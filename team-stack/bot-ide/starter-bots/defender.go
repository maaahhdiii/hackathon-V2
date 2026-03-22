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

func main() {
	target := env("MY_TARGET", "http://localhost:9100")
	vulns := []string{"sql_injection", "xss", "csrf", "rce", "auth_bypass"}
	services := []string{"web", "api", "file", "db"}

	fmt.Println("[defender.go] started")
	for {
		v := vulns[rand.Intn(len(vulns))]
		s := services[rand.Intn(len(services))]
		a := "enable"
		if rand.Intn(2) == 0 {
			a = "disable"
		}
		body, _ := json.Marshal(map[string]string{
			"service":            s,
			"vulnerability_type": v,
			"action":             a,
		})
		resp, err := http.Post(target+"/"+s+"/defend", "application/json", bytes.NewBuffer(body))
		if err != nil {
			fmt.Println("defend error:", err)
		} else {
			fmt.Println("defend", s, v, a, "->", resp.StatusCode)
			resp.Body.Close()
		}
		time.Sleep(4 * time.Second)
	}
}
