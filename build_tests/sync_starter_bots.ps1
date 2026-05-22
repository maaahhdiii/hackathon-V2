$files = @{
    'attacker.java' = @'
class attacker {
    public static void main(String[] args) {
        // empty starter
    }
}
'@
    'defender.java' = @'
class defender {
    public static void main(String[] args) {
        // empty starter
    }
}
'@
    'attacker.py' = @'
"""
Empty starter attacker bot - intentionally does nothing.
"""

def main():
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@
    'defender.py' = @'
"""
Empty starter defender bot - intentionally does nothing.
"""

def main():
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@
    'attacker.sh' = @'
#!/bin/sh
# empty starter attacker script
exit 0
'@
    'defender.sh' = @'
#!/bin/sh
# empty starter defender script
exit 0
'@
    'attacker.c' = @'
#include <stdio.h>

int main(void) { return 0; }
'@
    'defender.c' = @'
#include <stdio.h>

int main(void) { return 0; }
'@
    'attacker.go' = @'
package main

func main() {}
'@
    'defender.go' = @'
package main

func main() {}
'@
    'attacker.js' = @'
// empty starter attacker
process.exit(0);
'@
    'defender.js' = @'
// empty starter defender
process.exit(0);
'@
}

for ($i = 1; $i -le 10; $i++) {
    $port = 8100 + ($i - 1)
    foreach ($name in $files.Keys) {
        $jsonPath = Join-Path $PSScriptRoot ("sync_{0}_{1}.json" -f $i, $name)
        $payload = @{ content = $files[$name] } | ConvertTo-Json -Compress
        Set-Content -Path $jsonPath -Value $payload -Encoding utf8
        curl.exe -sS -X POST ("http://localhost:{0}/api/files/{1}" -f $port, $name) -H "Content-Type: application/json" --data-binary "@$jsonPath" | Out-Null
        Remove-Item -Path $jsonPath -ErrorAction SilentlyContinue
    }
}

Write-Output 'synced empty starter bots to team1-team10 IDEs'