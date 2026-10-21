package cl.duoc.pedidos360.insights.infrastructure;
import cl.duoc.pedidos360.insights.application.ProjectionStore;
import cl.duoc.pedidos360.messaging.OrderRegisteredV1;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.*;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.*;
import tools.jackson.databind.json.JsonMapper;

/** Single writer per directory. Each event is durable before ACK; identity conflicts fail closed. */
public class FileProjectionStore implements ProjectionStore {
    private final Path directory;
    private final JsonMapper json;
    public FileProjectionStore(Path directory,JsonMapper json) throws IOException {
        this.directory=directory.toAbsolutePath().normalize();this.json=json;Files.createDirectories(this.directory);
    }
    public synchronized boolean saveOnce(OrderRegisteredV1 event) throws IOException {
        Path target=directory.resolve(event.eventId()+".json");
        if (Files.exists(target)) {
            if (!event.equals(json.readValue(Files.readAllBytes(target),OrderRegisteredV1.class)))
                throw new IllegalArgumentException("Conflicting event identity");
            return false;
        }
        Path temporary=Files.createTempFile(directory,"projection-",".tmp");
        try {
            Files.setPosixFilePermissions(temporary,PosixFilePermissions.fromString("rw-------"));
            try (var channel=FileChannel.open(temporary,StandardOpenOption.WRITE)) {
                var buffer=ByteBuffer.wrap(json.writeValueAsBytes(event));
                while (buffer.hasRemaining()) channel.write(buffer);
                channel.force(true);
            }
            Files.move(temporary,target,StandardCopyOption.ATOMIC_MOVE);
            try (var parent=FileChannel.open(directory,StandardOpenOption.READ)) { parent.force(true); }
            return true;
        } finally { Files.deleteIfExists(temporary); }
    }
    public synchronized List<OrderRegisteredV1> findByTenant(String tenant) throws IOException {
        var result=new ArrayList<OrderRegisteredV1>();
        try (var paths=Files.list(directory)) {
            for (var path:paths.filter(p -> p.toString().endsWith(".json") && Files.isRegularFile(p)).toList()) {
                var event=json.readValue(Files.readAllBytes(path),OrderRegisteredV1.class);
                if (tenant.equals(event.tenantId())) result.add(event);
            }
        }
        result.sort(Comparator.comparing(OrderRegisteredV1::occurredAt).thenComparing(OrderRegisteredV1::eventId));
        return List.copyOf(result);
    }
}
