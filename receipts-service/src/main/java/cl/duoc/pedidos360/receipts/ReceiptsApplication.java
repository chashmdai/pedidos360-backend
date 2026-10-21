package cl.duoc.pedidos360.receipts;
import cl.duoc.pedidos360.messaging.*;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;
@SpringBootApplication
@Import({MessagingConfiguration.class, AdministrativeSecurity.class})
public class ReceiptsApplication {
    public static void main(String[] args) { SpringApplication.run(ReceiptsApplication.class,args); }
}
