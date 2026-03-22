import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URI;
import java.net.URL;
import java.util.Random;

public class defender {
    public static void main(String[] args) throws Exception {
        String target = System.getenv().getOrDefault("MY_TARGET", "http://localhost:9100");
        String[] vulns = {"sql_injection", "xss", "csrf", "rce", "auth_bypass"};
        String[] services = {"web", "api", "file", "db"};
        Random rnd = new Random();

        System.out.println("[defender.java] started");
        while (true) {
            String vuln = vulns[rnd.nextInt(vulns.length)];
            String service = services[rnd.nextInt(services.length)];
            String action = rnd.nextBoolean() ? "enable" : "disable";
            String body = String.format("{\"service\":\"%s\",\"vulnerability_type\":\"%s\",\"action\":\"%s\"}", service, vuln, action);

            try {
                URL url = URI.create(target + "/" + service + "/defend").toURL();
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("POST");
                conn.setRequestProperty("Content-Type", "application/json");
                conn.setDoOutput(true);
                try (OutputStream os = conn.getOutputStream()) {
                    os.write(body.getBytes());
                }
                System.out.println("defend " + service + "/" + vuln + "/" + action + " -> " + conn.getResponseCode());
            } catch (Exception e) {
                System.out.println("defend error: " + e.getMessage());
            }

            Thread.sleep(4000);
        }
    }
}
