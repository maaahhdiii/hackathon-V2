import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Random;

public class attacker {
    public static void main(String[] args) throws Exception {
        String target = System.getenv().getOrDefault("MY_TARGET", "http://localhost:9100");
        String secret = System.getenv().getOrDefault("HACKATHON_SECRET", "HACKATHON_SECRET_2025");
        String[] vulns = {"sql_injection", "xss", "csrf", "rce", "auth_bypass"};
        String[] services = {"web", "dns", "mail"};
        Random rnd = new Random();

        System.out.println("[attacker.java] started");
        while (true) {
            String vuln = vulns[rnd.nextInt(vulns.length)];
            String service = services[rnd.nextInt(services.length)];
            String body = String.format("{\"vulnerability_type\":\"%s\",\"service\":\"%s\",\"secret\":\"%s\"}", vuln, service, secret);

            try {
                URL url = new URL(target + "/attack");
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("POST");
                conn.setRequestProperty("Content-Type", "application/json");
                conn.setDoOutput(true);
                try (OutputStream os = conn.getOutputStream()) {
                    os.write(body.getBytes());
                }
                System.out.println("attack " + service + "/" + vuln + " -> " + conn.getResponseCode());
            } catch (Exception e) {
                System.out.println("attack error: " + e.getMessage());
            }

            Thread.sleep(3000);
        }
    }
}
