package cl.duoc.pedidos360.catalog.infrastructure.persistence;
import org.springframework.data.jpa.repository.JpaRepository;
interface JpaProducts extends JpaRepository<ProductEntity, String> {}
