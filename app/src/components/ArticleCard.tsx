import { Link } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";
import type { Article } from "@/types/article";
import { Badge } from "@/components/Badge";
import { Thumbnail } from "@/components/Thumbnail";
import { dateLabel } from "@/lib/format";

export function ArticleCard({ a }: { a: Article }) {
  return (
    <Link href={`/article/${a.id}`} asChild>
      <Pressable style={styles.card}>
        <Thumbnail a={a} />
        <View style={styles.body}>
          <View style={styles.top}>
            <Badge importance={a.importance} />
            <Text style={styles.source} numberOfLines={1}>
              {a.source || a.provider || ""}
            </Text>
            <Text style={styles.date}>{dateLabel(a.published_at)}</Text>
          </View>
          <Text style={styles.title} numberOfLines={3}>
            {a.title || "(無題)"}
          </Text>
          {!!a.summary && (
            <Text style={styles.summary} numberOfLines={2}>
              {a.summary}
            </Text>
          )}
        </View>
      </Pressable>
    </Link>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: "row",
    gap: 12,
    padding: 12,
    backgroundColor: "#fff",
    borderRadius: 12,
    marginBottom: 10,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: "#e4e7ec",
  },
  body: { flex: 1, gap: 4 },
  top: { flexDirection: "row", alignItems: "center", gap: 8 },
  source: { flex: 1, fontSize: 12, color: "#475467", fontWeight: "600" },
  date: { fontSize: 12, color: "#98a2b3" },
  title: { fontSize: 15, fontWeight: "700", color: "#101828" },
  summary: { fontSize: 13, color: "#475467", lineHeight: 18 },
});
