package websocket

import (
	"encoding/json"
	"log"
	"net/http"
	"sync"
	"time"

	"quant-feed/config"
	"quant-feed/redis"

	goredis "github.com/go-redis/redis/v8"
	"github.com/gorilla/websocket"
)

var upgrader = websocket.Upgrader{
	ReadBufferSize:  1024,
	WriteBufferSize: 1024,
	CheckOrigin: func(r *http.Request) bool {
		return true
	},
}

type Server struct {
	cfg     *config.Config
	redis   *redis.Client
	clients map[*Client]bool
	mu      sync.RWMutex
	stopCh  chan struct{}
}

type Client struct {
	conn *websocket.Conn
	send chan []byte
}

type RiskFactorData struct {
	Type   string             `json:"type"`
	Symbol string             `json:"symbol"`
	Data   map[string]float64 `json:"data"`
}

type WeightUpdateMessage struct {
	Type      string             `json:"type"`
	Weights   map[string]float64 `json:"weights"`
	Timestamp int64              `json:"timestamp"`
}

type PortfolioUpdateMessage struct {
	Type      string      `json:"type"`
	Data      interface{} `json:"data"`
	Timestamp int64       `json:"timestamp"`
}

func NewServer(cfg *config.Config, redisClient *redis.Client) *Server {
	return &Server{
		cfg:     cfg,
		redis:   redisClient,
		clients: make(map[*Client]bool),
		stopCh:  make(chan struct{}),
	}
}

func (s *Server) Start() {
	http.HandleFunc("/ws", s.handleWebSocket)
	go s.broadcastRiskFactors()
	go s.subscribePortfolioUpdates()

	log.Printf("WebSocket server starting on %s", s.cfg.WebSocketPort)
	if err := http.ListenAndServe(s.cfg.WebSocketPort, nil); err != nil {
		log.Fatalf("WebSocket server error: %v", err)
	}
}

func (s *Server) Stop() {
	close(s.stopCh)
	s.mu.Lock()
	defer s.mu.Unlock()
	for client := range s.clients {
		close(client.send)
	}
}

func (s *Server) handleWebSocket(w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("Failed to upgrade connection: %v", err)
		return
	}

	client := &Client{
		conn: conn,
		send: make(chan []byte, 512),
	}

	s.mu.Lock()
	s.clients[client] = true
	s.mu.Unlock()

	log.Printf("New WebSocket client connected, total: %d", len(s.clients))

	go s.readPump(client)
	go s.writePump(client)
}

func (s *Server) readPump(client *Client) {
	defer func() {
		s.mu.Lock()
		delete(s.clients, client)
		s.mu.Unlock()
		client.conn.Close()
		log.Printf("Client disconnected, total: %d", len(s.clients))
	}()

	for {
		_, message, err := client.conn.ReadMessage()
		if err != nil {
			break
		}

		s.handleClientMessage(message)
	}
}

func (s *Server) handleClientMessage(rawMsg []byte) {
	var baseMsg struct {
		Type string `json:"type"`
	}

	if err := json.Unmarshal(rawMsg, &baseMsg); err != nil {
		log.Printf("Failed to parse client message: %v", err)
		return
	}

	switch baseMsg.Type {
	case "weight_update":
		var weightMsg WeightUpdateMessage
		if err := json.Unmarshal(rawMsg, &weightMsg); err != nil {
			log.Printf("Failed to parse weight_update message: %v", err)
			return
		}
		s.forwardWeightUpdate(&weightMsg)

	default:
		log.Printf("Unknown message type from client: %s", baseMsg.Type)
	}
}

func (s *Server) forwardWeightUpdate(msg *WeightUpdateMessage) {
	if msg.Weights == nil || len(msg.Weights) == 0 {
		return
	}

	jsonData, err := json.Marshal(msg)
	if err != nil {
		log.Printf("Failed to marshal weight message: %v", err)
		return
	}

	redisClient := s.redis.GetGoRedisClient()
	ctx := s.redis.GetContext()

	if err := redisClient.Publish(ctx, "channel:weights", jsonData).Err(); err != nil {
		log.Printf("Failed to publish weight update to Redis: %v", err)
	}
}

func (s *Server) subscribePortfolioUpdates() {
	redisClient := s.redis.GetGoRedisClient()
	ctx := s.redis.GetContext()

	pubsub := redisClient.Subscribe(ctx, "channel:portfolio_update")
	defer pubsub.Close()

	ch := pubsub.Channel()

	log.Println("Subscribed to portfolio updates")

	for {
		select {
		case msg, ok := <-ch:
			if !ok {
				log.Println("Portfolio update channel closed")
				return
			}
			s.broadcastPortfolioUpdate([]byte(msg.Payload))
		case <-s.stopCh:
			return
		}
	}
}

func (s *Server) broadcastPortfolioUpdate(data []byte) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	if len(s.clients) == 0 {
		return
	}

	for client := range s.clients {
		select {
		case client.send <- data:
		default:
			log.Printf("Client send buffer full, dropping portfolio update")
		}
	}
}

func (s *Server) writePump(client *Client) {
	defer client.conn.Close()

	for message := range client.send {
		err := client.conn.WriteMessage(websocket.TextMessage, message)
		if err != nil {
			break
		}
	}
}

func (s *Server) broadcastRiskFactors() {
	ticker := time.NewTicker(200 * time.Millisecond)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			s.broadcastAllRiskFactors()
		case <-s.stopCh:
			return
		}
	}
}

func (s *Server) broadcastAllRiskFactors() {
	s.mu.RLock()
	defer s.mu.RUnlock()

	if len(s.clients) == 0 {
		return
	}

	marketData, err := s.redis.GetAllMarketData()
	if err != nil {
		return
	}

	for _, md := range marketData {
		factors, err := s.redis.GetRiskFactors(md.Symbol)
		if err != nil || len(factors) == 0 {
			continue
		}

		data := RiskFactorData{
			Type:   "risk_factor",
			Symbol: md.Symbol,
			Data:   factors,
		}

		jsonData, err := json.Marshal(data)
		if err != nil {
			continue
		}

		for client := range s.clients {
			select {
			case client.send <- jsonData:
			default:
			}
		}
	}
}

func (s *Server) Broadcast(message []byte) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	for client := range s.clients {
		select {
		case client.send <- message:
		default:
		}
	}
}

func (s *Server) GetGoRedisClient() *goredis.Client {
	return s.redis.GetGoRedisClient()
}
