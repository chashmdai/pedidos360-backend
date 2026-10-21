package cl.duoc.pedidos360.receipts.infrastructure;

import cl.duoc.pedidos360.messaging.OrderRegisteredV1;
import cl.duoc.pedidos360.receipts.application.ReceiptStore;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.*;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.json.JsonMapper;

@Repository
public class FileReceiptStore implements ReceiptStore {
    private final Path directory;
    private final JsonMapper json;
    public FileReceiptStore(@Value("${pedidos.receipts.directory}") String directory, JsonMapper json) throws IOException {
        this.directory=Path.of(directory).toAbsolutePath().normalize(); this.json=json;
        Files.createDirectories(this.directory);
    }
    public synchronized boolean saveOnce(OrderRegisteredV1 event) throws IOException {
        Path destination=directory.resolve(event.eventId()+".json");
        if (Files.exists(destination)) {
            var stored=json.readValue(Files.readAllBytes(destination),OrderRegisteredV1.class);
            if (!stored.equals(event)) throw new IllegalArgumentException("Conflicting event identity");
            return false;
        }
        Path temporary=Files.createTempFile(directory,"receipt-",".tmp");
        try {
            Files.setPosixFilePermissions(temporary,PosixFilePermissions.fromString("rw-------"));
            try (var channel=FileChannel.open(temporary,StandardOpenOption.WRITE)) {
                var buffer=ByteBuffer.wrap(json.writeValueAsBytes(event));
                while (buffer.hasRemaining()) channel.write(buffer);
                channel.force(true);
            }
            Files.move(temporary,destination,StandardCopyOption.ATOMIC_MOVE);
            try (var parent=FileChannel.open(directory,StandardOpenOption.READ)) { parent.force(true); }
            return true;
        } finally { Files.deleteIfExists(temporary); }
    }
    public synchronized List<OrderRegisteredV1> findByTenant(String tenant) throws IOException {
        var result=new ArrayList<OrderRegisteredV1>();
        try (var paths=Files.list(directory)) {
            for (var path:paths.filter(p -> p.toString().endsWith(".json") && Files.isRegularFile(p)).toList()) {
                var receipt=json.readValue(Files.readAllBytes(path),OrderRegisteredV1.class);
                if (tenant.equals(receipt.tenantId())) result.add(receipt);
            }
        }
        return List.copyOf(result);
    }
}
