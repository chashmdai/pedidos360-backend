package cl.duoc.pedidos360.rabbitadmin;
import cl.duoc.pedidos360.messaging.AdministrativeSecurity;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;
@SpringBootApplication
@Import(AdministrativeSecurity.class)
public class RabbitAdminApplication {
    public static void main(String[] args) { SpringApplication.run(RabbitAdminApplication.class,args); }
}
