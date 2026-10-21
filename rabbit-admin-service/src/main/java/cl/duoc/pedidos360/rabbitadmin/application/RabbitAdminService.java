package cl.duoc.pedidos360.rabbitadmin.application;

import cl.duoc.pedidos360.rabbitadmin.api.AdminRequests.*;
import java.net.URI;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.web.client.*;
import org.springframework.web.server.ResponseStatusException;

/** All broker details and protected namespace rules stay behind this application service. */
@Service
public class RabbitAdminService {
    public record Result(boolean created, Object resource) {}
    private final RestClient broker;
    private final String vhost;
    private final String prefix;
    public RabbitAdminService(RestClient broker,@Value("${pedidos.rabbit-admin.vhost}") String vhost,
            @Value("${pedidos.rabbit-admin.allowed-prefix}") String prefix) {
        this.broker=broker; this.vhost=vhost; this.prefix=prefix;
    }
    private void allowed(String name) {
        if (name==null || !name.startsWith(prefix) || name.length()<=prefix.length())
            throw new ResponseStatusException(HttpStatus.FORBIDDEN,"Only disposable laboratory resources may be managed");
    }
    private String[] path(String kind,String name) { return new String[]{"api",kind,vhost,name}; }
    @SuppressWarnings("unchecked")
    private Object request(HttpMethod method,String[] path,Object body,boolean nullable) {
        try {
            var call=broker.method(method).uri(builder -> builder.pathSegment(path).build());
            if (body!=null) call.contentType(MediaType.APPLICATION_JSON).body(body);
            return call.retrieve().body(Object.class);
        } catch (RestClientResponseException error) {
            int status=error.getStatusCode().value();
            if (status==404 && nullable) return null;
            if (status==404) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Broker resource not found");
            if (status==400 || status==409) throw new ResponseStatusException(HttpStatus.CONFLICT,"Broker resource has incompatible settings or is in use");
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,"Broker management request failed");
        } catch (RestClientException error) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,"Broker management unavailable");
        }
    }
    @SuppressWarnings("unchecked")
    private Map<String,Object> resource(String kind,String name,boolean nullable) {
        allowed(name);
        return (Map<String,Object>)request(HttpMethod.GET,path(kind,name),null,nullable);
    }
    public Map<String,Object> getQueue(String name) { return resource("queues",name,false); }
    public Map<String,Object> getExchange(String name) { return resource("exchanges",name,false); }
    private void equivalent(Map<String,Object> existing,Map<String,Object> desired) {
        if (existing!=null && desired.entrySet().stream().anyMatch(e -> !Objects.equals(existing.get(e.getKey()),e.getValue())))
            throw new ResponseStatusException(HttpStatus.CONFLICT,"Immutable settings differ; use a new laboratory resource name");
    }
    public Result createQueue(QueueRequest dto) {
        allowed(dto.name());
        var args=new HashMap<String,Object>(); args.put("x-queue-type","classic");
        if (dto.messageTtl()!=null) args.put("x-message-ttl",dto.messageTtl());
        if (dto.maxLength()!=null) args.put("x-max-length",dto.maxLength());
        var desired=Map.<String,Object>of("durable",dto.durable(),"auto_delete",dto.autoDelete(),"arguments",args);
        var existing=resource("queues",dto.name(),true); equivalent(existing,desired);
        request(HttpMethod.PUT,path("queues",dto.name()),desired,false);
        return new Result(existing==null, getQueue(dto.name()));
    }
    public Result createExchange(ExchangeRequest dto) {
        allowed(dto.name());
        var desired=Map.<String,Object>of("type",dto.type(),"durable",dto.durable(),"auto_delete",dto.autoDelete(),"internal",false,"arguments",Map.of());
        var existing=resource("exchanges",dto.name(),true); equivalent(existing,desired);
        request(HttpMethod.PUT,path("exchanges",dto.name()),desired,false);
        return new Result(existing==null,getExchange(dto.name()));
    }
    public void deleteQueue(String name) {
        var info=getQueue(name);
        // Management counters may lag: broker-side if-empty/if-unused is the final guard.
        deleteGuarded("queues",name,true);
    }
    public void deleteExchange(String name) { getExchange(name); deleteGuarded("exchanges",name,false); }
    private void deleteGuarded(String kind,String name,boolean queue) {
        try {
            broker.delete().uri(b -> {
                b.pathSegment(path(kind,name)).queryParam("if-unused",true);
                if (queue) b.queryParam("if-empty",true);
                return b.build();
            }).retrieve().toBodilessEntity();
        } catch (RestClientResponseException error) {
            if (error.getStatusCode().value()==404) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Broker resource not found");
            if (error.getStatusCode().is4xxClientError()) throw new ResponseStatusException(HttpStatus.CONFLICT,"Resource is in use; data was preserved");
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,"Broker management failed");
        } catch (RestClientException error) { throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,"Broker management unavailable"); }
    }
    @SuppressWarnings("unchecked")
    public List<Map<String,Object>> bindings(String exchange,String queue) {
        getExchange(exchange); getQueue(queue);
        return (List<Map<String,Object>>)request(HttpMethod.GET,new String[]{"api","bindings",vhost,"e",exchange,"q",queue},null,false);
    }
    public Result createBinding(BindingRequest dto) {
        var matches=bindings(dto.exchange(),dto.queue()).stream().filter(b -> dto.routingKey().equals(b.get("routing_key"))).toList();
        if (!matches.isEmpty()) return new Result(false,matches.getFirst());
        request(HttpMethod.POST,new String[]{"api","bindings",vhost,"e",dto.exchange(),"q",dto.queue()},
                Map.of("routing_key",dto.routingKey(),"arguments",Map.of()),false);
        return new Result(true,Map.of("exchange",dto.exchange(),"queue",dto.queue(),"routingKey",dto.routingKey()));
    }
    public void deleteBinding(BindingRequest dto) {
        var match=bindings(dto.exchange(),dto.queue()).stream().filter(b -> dto.routingKey().equals(b.get("routing_key"))).findFirst()
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND,"Binding not found"));
        request(HttpMethod.DELETE,new String[]{"api","bindings",vhost,"e",dto.exchange(),"q",dto.queue(),match.get("properties_key").toString()},null,false);
    }
}
