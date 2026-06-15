package websocket

import (
	"encoding/json"
	"log"
	"net/http"
	"sync"
	"time"

	"quant-feed/config"
	"quant-feed/redis"

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
		send: make(chan []byte, 256),
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
		_, _, err := client.conn.ReadMessage()
		if err != nil {
			break
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
