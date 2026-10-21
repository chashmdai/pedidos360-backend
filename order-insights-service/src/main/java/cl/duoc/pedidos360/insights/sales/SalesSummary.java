package cl.duoc.pedidos360.insights.sales;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.*;
/** Pure read model: amounts in different currencies are never added together. */
public final class SalesSummary {
    private SalesSummary() {}
    public record Sale(LocalDate day,String currency,BigDecimal amount) {}
    public record Summary(LocalDate day,String currency,long orders,BigDecimal total) {}
    private record Key(LocalDate day,String currency) {}
    public static List<Summary> summarize(List<Sale> sales) {
        var totals=new HashMap<Key,Summary>();
        for (var sale:sales) {
            var key=new Key(sale.day(),sale.currency());
            var old=totals.getOrDefault(key,new Summary(key.day(),key.currency(),0,BigDecimal.ZERO));
            totals.put(key,new Summary(key.day(),key.currency(),old.orders()+1,old.total().add(sale.amount())));
        }
        return totals.values().stream().sorted(Comparator.comparing(Summary::day).thenComparing(Summary::currency)).toList();
    }
}
