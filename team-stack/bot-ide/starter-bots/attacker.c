#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

int main(void) {
    const char *target = getenv("MY_TARGET");
    const char *secret = getenv("HACKATHON_SECRET");
    if (!target) target = "http://localhost:9100";
    if (!secret) secret = "HACKATHON_SECRET_2025";

    const char *vulns[] = {"sql_injection", "xss", "csrf", "rce", "auth_bypass"};
    const char *services[] = {"web", "api", "file", "db"};

    srand((unsigned int)time(NULL));
    printf("[attacker.c] started\n");

    while (1) {
        const char *v = vulns[rand() % 5];
        const char *s = services[rand() % 4];
        char cmd[1024];
        snprintf(cmd, sizeof(cmd),
            "curl -s -X POST %s/%s/attack -H 'Content-Type: application/json' -d '{\"vulnerability_type\":\"%s\",\"service\":\"%s\",\"secret\":\"%s\"}'",
            target, s, v, s, secret);
        int rc = system(cmd);
        printf("attack %s/%s -> rc=%d\n", s, v, rc);
        sleep(3);
    }

    return 0;
}
