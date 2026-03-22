#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>

int main(void) {
    const char *target = getenv("MY_TARGET");
    if (!target) target = "http://localhost:9100";

    const char *vulns[] = {"sql_injection", "xss", "csrf", "rce", "auth_bypass"};
    const char *services[] = {"web", "api", "file", "db"};

    srand((unsigned int)time(NULL));
    printf("[defender.c] started\n");

    while (1) {
        const char *v = vulns[rand() % 5];
        const char *s = services[rand() % 4];
        const char *a = (rand() % 2) ? "enable" : "disable";
        char cmd[1024];
        snprintf(cmd, sizeof(cmd),
            "curl -s -X POST %s/%s/defend -H 'Content-Type: application/json' -d '{\"service\":\"%s\",\"vulnerability_type\":\"%s\",\"action\":\"%s\"}'",
            target, s, s, v, a);
        int rc = system(cmd);
        printf("defend %s/%s/%s -> rc=%d\n", s, v, a, rc);
        sleep(4);
    }

    return 0;
}
