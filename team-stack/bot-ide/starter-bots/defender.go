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

func main() {
	target := env("MY_TARGET", "http://localhost:9100")
	secret := env("HACKATHON_SECRET", "HACKATHON_SECRET_2025")
	services := map[string][]string{
		"web":  {"sqli", "xss", "auth_bypass"},
		"api":  {"insecure_ep", "cmd_inject", "idor"},
		"file": {"path_traversal", "exec_upload"},
		"db":   {"sqli", "priv_esc"},
	}

	fmt.Println("[defender.go] started")
	for {
		for service, vulns := range services {
			for _, vuln := range vulns {
				body, _ := json.Marshal(map[string]string{"secret": secret, "vuln": vuln})
				resp, err := http.Post(target+"/"+service+"/flags/deactivate", "application/json", bytes.NewBuffer(body))
				if err != nil {
					fmt.Println("defend error:", err)
				} else {
					fmt.Println("deactivate", service, vuln, "->", resp.StatusCode)
					resp.Body.Close()
				}
			}
			healBody, _ := json.Marshal(map[string]any{"secret": secret, "amount": 5})
			resp, err := http.Post(target+"/"+service+"/heal", "application/json", bytes.NewBuffer(healBody))
			if err != nil {
				fmt.Println("heal error:", err)
			} else {
				fmt.Println("heal", service, "->", resp.StatusCode)
				resp.Body.Close()
			}
		}
		time.Sleep(4 * time.Second)
	}
}
