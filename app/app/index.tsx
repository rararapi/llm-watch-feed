import { useMemo, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  SectionList,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { Link } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useArticles } from "@/api/client";
import { ArticleCard } from "@/components/ArticleCard";
import { Filters } from "@/components/Filters";
import {
  INITIAL_FILTER,
  filterArticles,
  groupByRecency,
  sourcesOf,
  type FilterState,
} from "@/lib/filter";

export default function FeedScreen() {
  const insets = useSafeAreaInsets();
  const { data, isLoading, isError, error, refetch, isRefetching } = useArticles();
  const [filter, setFilter] = useState<FilterState>(INITIAL_FILTER);

  const articles = data ?? [];
  const sources = useMemo(() => sourcesOf(articles), [articles]);
  const filtered = useMemo(() => filterArticles(articles, filter), [articles, filter]);
  const sections = useMemo(
    () => groupByRecency(filtered).map((g) => ({ title: g.label, data: g.articles })),
    [filtered],
  );

  if (isLoading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator />
      </View>
    );
  }

  if (isError && articles.length === 0) {
    return (
      <View style={styles.center}>
        <Text style={styles.errTitle}>読み込みに失敗しました</Text>
        <Text style={styles.errBody}>{(error as Error)?.message ?? "ネットワークを確認してください"}</Text>
        <Pressable style={styles.retry} onPress={() => refetch()}>
          <Text style={styles.retryText}>再試行</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <SectionList
      style={styles.list}
      contentContainerStyle={{ padding: 12, paddingBottom: insets.bottom + 24 }}
      sections={sections}
      keyExtractor={(item) => item.id}
      stickySectionHeadersEnabled={false}
      refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={() => refetch()} />}
      ListHeaderComponent={
        <View>
          <Link href="/subscribe" asChild>
            <Pressable style={styles.subscribe}>
              <Text style={styles.subscribeText}>RSSで購読する →</Text>
            </Pressable>
          </Link>
          <Filters
            state={filter}
            sources={sources}
            resultCount={filtered.length}
            onChange={setFilter}
          />
        </View>
      }
      renderSectionHeader={({ section }) => <Text style={styles.section}>{section.title}</Text>}
      renderItem={({ item }) => <ArticleCard a={item} />}
      ListEmptyComponent={<Text style={styles.empty}>該当する記事がありません</Text>}
    />
  );
}

const styles = StyleSheet.create({
  list: { backgroundColor: "#f5f6f8" },
  center: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24, gap: 8 },
  section: { fontSize: 13, fontWeight: "700", color: "#667085", marginTop: 12, marginBottom: 6 },
  subscribe: {
    backgroundColor: "#fff",
    borderRadius: 10,
    padding: 12,
    marginBottom: 10,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: "#e4e7ec",
  },
  subscribeText: { color: "#175cd3", fontWeight: "600" },
  empty: { textAlign: "center", color: "#98a2b3", marginTop: 32 },
  errTitle: { fontSize: 16, fontWeight: "700", color: "#101828" },
  errBody: { fontSize: 13, color: "#667085", textAlign: "center" },
  retry: { marginTop: 8, paddingHorizontal: 16, paddingVertical: 8, backgroundColor: "#175cd3", borderRadius: 8 },
  retryText: { color: "#fff", fontWeight: "600" },
});
