package cl.duoc.pedidos360.kafkaadmin.application;

import cl.duoc.pedidos360.kafka.KafkaTopicProperties;
import cl.duoc.pedidos360.kafkaadmin.api.AdminRequests.CreateTopic;
import java.util.*;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;
import org.apache.kafka.clients.admin.*;
import org.apache.kafka.common.GroupState;
import org.apache.kafka.common.KafkaFuture;
import org.apache.kafka.common.Node;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.config.ConfigResource;
import org.apache.kafka.common.errors.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

/**
 * All AdminClient details and protection rules (report section 10, table 14) stay behind this service:
 * create, increase partitions and delete only for the laboratory prefix; business and internal topics are
 * protected (409); configuration changes accept only a whitelist with bounded values.
 */
@Service
public class KafkaAdminService {
    /** Table 14: the only configurations PATCH may change. */
    public static final Set<String> CONFIG_WHITELIST = Set.of("retention.ms", "cleanup.policy", "min.insync.replicas", "segment.ms", "max.message.bytes");
    private static final Set<String> CLEANUP_POLICIES = Set.of("delete", "compact", "compact,delete", "delete,compact");
    private static final String NAME = "[a-zA-Z0-9._-]{1,249}";

    public record Broker(int id, String host, int port, String rack) {}
    public record Cluster(String clusterId, Broker controller, List<Broker> brokers) {}
    public record TopicSummary(String name, int partitions, int replicationFactor, boolean internal) {}
    public record PartitionInfo(int partition, Integer leader, List<Integer> replicas, List<Integer> isr) {}
    public record ConfigValue(String value, String source) {}
    public record TopicDetail(String name, boolean internal, boolean protectedTopic, int replicationFactor,
                              List<PartitionInfo> partitions, Map<String, ConfigValue> configs) {}
    public record GroupSummary(String groupId, String state, int members, String assignor) {}
    public record Member(String memberId, String clientId, String host, List<String> assignment) {}
    public record PartitionLag(String topic, int partition, Long committedOffset, long logEndOffset, Long lag, String memberId) {}
    public record GroupDetail(String groupId, String state, String assignor, Broker coordinator, List<Member> members,
                              List<PartitionLag> partitions, long totalLag) {}

    private final Admin admin;
    private final String labPrefix;
    private final Set<String> businessTopics;
    private final long timeoutMs;

    public KafkaAdminService(Admin admin, KafkaTopicProperties topics,
                             @Value("${pedidos.kafka-admin.allowed-prefix}") String labPrefix,
                             @Value("${pedidos.kafka-admin.api-timeout-ms:10000}") long timeoutMs) {
        this.admin = admin; this.labPrefix = labPrefix; this.timeoutMs = timeoutMs;
        this.businessTopics = Set.of(topics.ordersRegistered(), topics.productMetrics(), topics.ordersRegisteredDlt(), topics.productMetricsDlt());
    }

    // ---------- rules ----------

    static ResponseStatusException status(HttpStatus status, String detail) { return new ResponseStatusException(status, detail); }

    void validName(String name) {
        if (name == null || !name.matches(NAME)) throw status(HttpStatus.BAD_REQUEST, "Invalid topic name");
    }

    boolean isLab(String name) { return name.startsWith(labPrefix) && name.length() > labPrefix.length(); }

    boolean isProtected(String name) { return businessTopics.contains(name) || name.startsWith("__") || !isLab(name); }

    /** Create / increase partitions / delete: only disposable laboratory topics. */
    void requireLab(String name) {
        validName(name);
        if (businessTopics.contains(name) || name.startsWith("__")) throw status(HttpStatus.CONFLICT, "Protected business or internal topic; data was preserved");
        if (!isLab(name)) throw status(HttpStatus.CONFLICT, "Only topics prefixed " + labPrefix + " may be modified this way");
    }

    /** Whitelisted keys with bounded values; returns them in a stable order. */
    static Map<String, String> validConfigs(Map<String, String> configs) {
        if (configs == null) return Map.of();
        var result = new TreeMap<String, String>();
        configs.forEach((key, raw) -> {
            if (!CONFIG_WHITELIST.contains(key)) throw status(HttpStatus.BAD_REQUEST, "Configuration not allowed: " + key);
            String value = raw == null ? "" : raw.trim();
            boolean ok = switch (key) {
                case "cleanup.policy" -> CLEANUP_POLICIES.contains(value);
                case "retention.ms" -> value.equals("-1") || between(value, 60_000L, 31_536_000_000L);
                case "segment.ms" -> between(value, 60_000L, 604_800_000L);
                case "min.insync.replicas" -> between(value, 1, 3);
                case "max.message.bytes" -> between(value, 1024, 10_485_760);
                default -> false;
            };
            if (!ok) throw status(HttpStatus.BAD_REQUEST, "Invalid value for " + key);
            result.put(key, value);
        });
        return result;
    }

    private static boolean between(String value, long min, long max) {
        try { long v = Long.parseLong(value); return v >= min && v <= max; } catch (NumberFormatException e) { return false; }
    }

    // ---------- AdminClient calls ----------

    <T> T await(KafkaFuture<T> future) {
        try {
            return future.get(timeoutMs, TimeUnit.MILLISECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw status(HttpStatus.SERVICE_UNAVAILABLE, "Interrupted");
        } catch (java.util.concurrent.TimeoutException e) {
            throw status(HttpStatus.SERVICE_UNAVAILABLE, "Kafka cluster did not respond");
        } catch (ExecutionException e) {
            throw translate(e.getCause());
        }
    }

    static ResponseStatusException translate(Throwable error) {
        if (error instanceof UnknownTopicOrPartitionException) return status(HttpStatus.NOT_FOUND, "Topic not found");
        if (error instanceof GroupIdNotFoundException) return status(HttpStatus.NOT_FOUND, "Consumer group not found");
        if (error instanceof TopicExistsException) return status(HttpStatus.CONFLICT, "Topic already exists");
        if (error instanceof InvalidReplicationFactorException || error instanceof InvalidPartitionsException
                || error instanceof InvalidConfigurationException || error instanceof InvalidRequestException
                || error instanceof PolicyViolationException || error instanceof InvalidTopicException) {
            return status(HttpStatus.BAD_REQUEST, error.getClass().getSimpleName());
        }
        return status(HttpStatus.SERVICE_UNAVAILABLE, "Kafka cluster unavailable");
    }

    static Broker broker(Node node) { return node == null ? null : new Broker(node.id(), node.host(), node.port(), node.rack()); }

    public Cluster cluster() {
        var result = admin.describeCluster();
        var brokers = await(result.nodes()).stream().map(KafkaAdminService::broker).sorted(Comparator.comparingInt(Broker::id)).toList();
        return new Cluster(await(result.clusterId()), broker(await(result.controller())), brokers);
    }

    public List<TopicSummary> topics(boolean includeInternal) {
        var names = await(admin.listTopics(new ListTopicsOptions().listInternal(includeInternal)).names());
        if (names.isEmpty()) return List.of();
        return await(admin.describeTopics(names).allTopicNames()).values().stream()
                .map(d -> new TopicSummary(d.name(), d.partitions().size(), d.partitions().getFirst().replicas().size(), d.isInternal()))
                .sorted(Comparator.comparing(TopicSummary::name)).toList();
    }

    public TopicDetail topic(String name) {
        validName(name);
        var description = await(admin.describeTopics(List.of(name)).allTopicNames()).get(name);
        var resource = new ConfigResource(ConfigResource.Type.TOPIC, name);
        var configs = new TreeMap<String, ConfigValue>();
        await(admin.describeConfigs(List.of(resource)).all()).get(resource).entries().stream()
                .filter(e -> !e.isSensitive())
                .forEach(e -> configs.put(e.name(), new ConfigValue(e.value(), e.source().name())));
        var partitions = description.partitions().stream().map(p -> new PartitionInfo(p.partition(), p.leader() == null ? null : p.leader().id(),
                p.replicas().stream().map(Node::id).toList(), p.isr().stream().map(Node::id).toList())).toList();
        return new TopicDetail(name, description.isInternal(), isProtected(name), description.partitions().getFirst().replicas().size(), partitions, configs);
    }

    public TopicDetail create(CreateTopic request) {
        validName(request.name());
        if (!isLab(request.name()) || businessTopics.contains(request.name())) {
            throw status(HttpStatus.BAD_REQUEST, "Topic name must start with " + labPrefix);
        }
        var topic = new NewTopic(request.name(), request.partitions(), request.replicationFactor().shortValue())
                .configs(validConfigs(request.configs()));
        await(admin.createTopics(List.of(topic)).all());
        return topic(request.name());
    }

    public TopicDetail updateConfigs(String name, Map<String, String> requested) {
        validName(name);
        if (name.startsWith("__")) throw status(HttpStatus.CONFLICT, "Internal topics cannot be reconfigured");
        var configs = validConfigs(requested);
        if (configs.isEmpty()) throw status(HttpStatus.BAD_REQUEST, "Provide at least one configuration");
        var current = topic(name);   // 404 if missing
        if (configs.containsKey("min.insync.replicas") && Integer.parseInt(configs.get("min.insync.replicas")) > current.replicationFactor()) {
            throw status(HttpStatus.BAD_REQUEST, "min.insync.replicas cannot exceed the replication factor");
        }
        var resource = new ConfigResource(ConfigResource.Type.TOPIC, name);
        var ops = configs.entrySet().stream().map(e -> new AlterConfigOp(new ConfigEntry(e.getKey(), e.getValue()), AlterConfigOp.OpType.SET)).toList();
        await(admin.incrementalAlterConfigs(Map.of(resource, ops)).all());
        return topic(name);
    }

    public TopicDetail increasePartitions(String name, int partitions) {
        requireLab(name);
        var current = topic(name).partitions().size();
        if (partitions <= current) throw status(HttpStatus.BAD_REQUEST, "Partitions can only increase (current " + current + ")");
        await(admin.createPartitions(Map.of(name, NewPartitions.increaseTo(partitions))).all());
        return topic(name);
    }

    public void delete(String name) {
        requireLab(name);
        topic(name);   // 404 if missing
        await(admin.deleteTopics(List.of(name)).all());
    }

    public List<GroupSummary> groups() {
        // Classic consumer groups (brokers 3.9 in ZooKeeper mode): filter by protocol type, no KIP-848 type filter.
        var ids = await(admin.listGroups(new ListGroupsOptions()).all()).stream()
                // Same selection as kafka-consumer-groups --list: consumer protocol, simple groups (offsets only) or KIP-848 groups.
                .filter(g -> "consumer".equals(g.protocol()) || g.isSimpleConsumerGroup() || g.type().map(t -> t.name().equals("CONSUMER")).orElse(false))
                .map(GroupListing::groupId).sorted().toList();
        if (ids.isEmpty()) return List.of();
        var descriptions = await(admin.describeConsumerGroups(ids).all());
        return ids.stream().map(descriptions::get).map(d -> new GroupSummary(d.groupId(), d.groupState().name(), d.members().size(), d.partitionAssignor())).toList();
    }

    public GroupDetail group(String groupId) {
        if (groupId == null || !groupId.matches("[a-zA-Z0-9._-]{1,249}")) throw status(HttpStatus.BAD_REQUEST, "Invalid group id");
        var description = await(admin.describeConsumerGroups(List.of(groupId)).all()).get(groupId);
        if (description.groupState() == GroupState.DEAD) throw status(HttpStatus.NOT_FOUND, "Consumer group not found");
        var committed = await(admin.listConsumerGroupOffsets(groupId).partitionsToOffsetAndMetadata());
        var owner = new HashMap<TopicPartition, String>();
        var members = description.members().stream().map(m -> {
            m.assignment().topicPartitions().forEach(tp -> owner.put(tp, m.consumerId()));
            return new Member(m.consumerId(), m.clientId(), m.host(), m.assignment().topicPartitions().stream()
                    .map(tp -> tp.topic() + "-" + tp.partition()).sorted().toList());
        }).sorted(Comparator.comparing(Member::clientId)).toList();
        var partitions = new TreeSet<TopicPartition>(Comparator.comparing(TopicPartition::topic).thenComparingInt(TopicPartition::partition));
        partitions.addAll(committed.keySet()); partitions.addAll(owner.keySet());
        var ends = partitions.isEmpty() ? Map.<TopicPartition, ListOffsetsResult.ListOffsetsResultInfo>of()
                : await(admin.listOffsets(partitions.stream().collect(Collectors.toMap(tp -> tp, tp -> OffsetSpec.latest()))).all());
        long total = 0;
        var lags = new ArrayList<PartitionLag>();
        for (var tp : partitions) {
            var offset = committed.get(tp);
            Long current = offset == null ? null : offset.offset();
            long end = ends.get(tp).offset();
            Long lag = current == null ? null : Math.max(0, end - current);
            if (lag != null) total += lag;
            lags.add(new PartitionLag(tp.topic(), tp.partition(), current, end, lag, owner.get(tp)));
        }
        return new GroupDetail(groupId, description.groupState().name(), description.partitionAssignor(), broker(description.coordinator()),
                members, lags, total);
    }
}
