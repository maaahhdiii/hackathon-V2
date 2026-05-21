#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>

int main(void) {
    const char *target = getenv("MY_TARGET");
    const char *secret = getenv("HACKATHON_SECRET");
    if (!target) target = "http://localhost:9100";
    if (!secret) secret = "HACKATHON_SECRET_2025";

    const char *service_vulns[][4] = {
        {"web", "sqli", "xss", "auth_bypass"},
        {"api", "insecure_ep", "cmd_inject", "idor"},
        {"file", "path_traversal", "exec_upload", NULL},
        {"db", "sqli", "priv_esc", NULL}
    };

    srand((unsigned int)time(NULL));
    printf("[defender.c] started\n");

    while (1) {
        for (int i = 0; i < 4; i++) {
            const char *s = service_vulns[i][0];
            for (int j = 1; service_vulns[i][j]; j++) {
                char cmd[1024];
                snprintf(cmd, sizeof(cmd),
                    "curl -s -X POST %s/%s/flags/deactivate -H 'Content-Type: application/json' -d '{\"secret\":\"%s\",\"vuln\":\"%s\"}' >/dev/null",
                    target, s, secret, service_vulns[i][j]);
                int rc = system(cmd);
                printf("deactivate %s/%s -> rc=%d\n", s, service_vulns[i][j], rc);
            }
            char heal[1024];
            snprintf(heal, sizeof(heal),
                "curl -s -X POST %s/%s/heal -H 'Content-Type: application/json' -d '{\"secret\":\"%s\",\"amount\":5}' >/dev/null",
                target, s, secret);
            int rc = system(heal);
            printf("heal %s -> rc=%d\n", s, rc);
        }
        sleep(4);
    }

    return 0;
}
