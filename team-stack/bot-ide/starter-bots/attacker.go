package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"math/rand"
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
		return "web"
	}
	return svc
}

func main() {
	orch := env("ORCH", env("ORCHESTRATOR_URL", "http://orchestrator:9000"))
	target := env("MY_TARGET", "http://localhost:9100")
	secret := env("HACKATHON_SECRET", "HACKATHON_SECRET_2025")
	vulns := []string{"sql_injection", "xss", "csrf", "rce", "auth_bypass"}

	fmt.Println("[attacker.go] started")
	for {
		svc := activeService(orch)
		v := vulns[rand.Intn(len(vulns))]
		body, _ := json.Marshal(map[string]string{
			"vulnerability_type": v,
			"service":            svc,
			"secret":             secret,
		})
		resp, err := http.Post(target+"/attack", "application/json", bytes.NewBuffer(body))
		if err != nil {
			fmt.Println("attack error:", err)
		} else {
			fmt.Println("attack", svc, v, "->", resp.StatusCode)
			resp.Body.Close()
		}
		time.Sleep(3 * time.Second)
	}
}
