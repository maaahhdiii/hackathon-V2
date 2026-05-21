import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URI;
import java.net.URL;

public class defender {
    private static String target = System.getenv().getOrDefault("MY_TARGET", "http://localhost:9100");
    private static String secret = System.getenv().getOrDefault("HACKATHON_SECRET", "HACKATHON_SECRET_2025");
    private static final String[][] SERVICE_VULNS = {
        {"web", "sqli", "xss", "auth_bypass"},
        {"api", "insecure_ep", "cmd_inject", "idor"},
        {"file", "path_traversal", "exec_upload"},
        {"db", "sqli", "priv_esc"}
    };

    private static int postJson(String path, String body) throws Exception {
        URL url = URI.create(target + path).toURL();
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setRequestMethod("POST");
        conn.setRequestProperty("Content-Type", "application/json");
        conn.setDoOutput(true);
        try (OutputStream os = conn.getOutputStream()) {
            os.write(body.getBytes());
        }
        return conn.getResponseCode();
    }

    public static void main(String[] args) throws Exception {
        System.out.println("[defender.java] started");
        while (true) {
            try {
                for (String[] entry : SERVICE_VULNS) {
                    String service = entry[0];
                    for (int i = 1; i < entry.length; i++) {
                        int code = postJson("/" + service + "/flags/deactivate", String.format("{\"secret\":\"%s\",\"vuln\":\"%s\"}", secret, entry[i]));
                        System.out.println("deactivate " + service + "/" + entry[i] + " -> " + code);
                    }
                    int healCode = postJson("/" + service + "/heal", String.format("{\"secret\":\"%s\",\"amount\":5}", secret));
                    System.out.println("heal " + service + " -> " + healCode);
                }
            } catch (Exception e) {
                System.out.println("defend error: " + e.getMessage());
            }

            Thread.sleep(4000);
        }
    }
}
