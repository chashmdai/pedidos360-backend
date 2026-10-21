package cl.duoc.pedidos360.orders.infrastructure.persistence;
import java.util.*;
import org.springframework.data.jpa.repository.JpaRepository;
interface JpaOrders extends JpaRepository<OrderEntity,String> {
    List<OrderEntity> findByOwnerTenantOrderByCreatedAtDesc(String tenant);
    List<OrderEntity> findByOwnerTenantAndOwnerSubjectOrderByCreatedAtDesc(String tenant,String subject);
    Optional<OrderEntity> findByIdAndOwnerTenantAndOwnerSubject(String id,String tenant,String subject);
}
