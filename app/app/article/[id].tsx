import { Share, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useLocalSearchParams, Stack } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useArticle } from "@/api/client";
import { Badge } from "@/components/Badge";
import { Thumbnail } from "@/components/Thumbnail";
import { dateLabel } from "@/lib/format";
import { modelTypeLabel } from "@/lib/meta";

export default function ArticleScreen() {
  const insets = useSafeAreaInsets();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { article: a, isLoading } = useArticle(id);

  if (!a) {
    return (
      <View style={styles.center}>
        <Text style={styles.muted}>{isLoading ? "読み込み中…" : "記事が見つかりません"}</Text>
      </View>
    );
  }

  const openOriginal = () =>
    WebBrowser.openBrowserAsync(a.url).catch(() => {
      /* opening the in-app browser must not crash the screen */
    });

  const share = () =>
    Share.share({ message: `${a.title}\n${a.url}`, url: a.url, title: a.title }).catch(() => {});

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={{ padding: 16, paddingBottom: insets.bottom + 32 }}
    >
      <Stack.Screen options={{ title: a.source || "記事" }} />
      <View style={styles.metaRow}>
        <Badge importance={a.importance} />
        <Text style={styles.source}>{a.source || a.provider || ""}</Text>
        <Text style={styles.date}>{dateLabel(a.published_at)}</Text>
      </View>
      <Text style={styles.title}>{a.title}</Text>

      {(a.image_generated_url || a.image_url) && (
        <View style={styles.hero}>
          <Thumbnail a={a} size={120} />
        </View>
      )}

      {!!a.summary && <Section title="要約" body={a.summary} />}
      {!!a.impact && <Section title="影響" body={a.impact} />}
      {!!a.action && <Section title="推奨アクション" body={a.action} />}

      {(a.model_type || (a.tags && a.tags.length > 0)) && (
        <View style={styles.chips}>
          {!!a.model_type && (
            <Chip text={a.model_type} hint={modelTypeLabel(a.model_type)} accent />
          )}
          {(a.tags ?? []).map((t) => (
            <Chip key={t} text={t} />
          ))}
        </View>
      )}

      <Pressable style={styles.primary} onPress={openOriginal}>
        <Text style={styles.primaryText}>元記事を開く</Text>
      </Pressable>
      <Pressable style={styles.secondary} onPress={share}>
        <Text style={styles.secondaryText}>共有</Text>
      </Pressable>
    </ScrollView>
  );
}

function Section({ title, body }: { title: string; body: string }) {
  return (
    <View style={styles.sectionBlock}>
      <Text style={styles.sectionTitle}>{title}</Text>
      <Text style={styles.sectionBody}>{body}</Text>
    </View>
  );
}

function Chip({ text, hint, accent }: { text: string; hint?: string; accent?: boolean }) {
  return (
    <View style={[styles.chip, accent && styles.chipAccent]}>
      <Text style={[styles.chipText, accent && styles.chipTextAccent]}>{text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { backgroundColor: "#f5f6f8" },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  muted: { color: "#98a2b3" },
  metaRow: { flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 8 },
  source: { flex: 1, fontSize: 13, color: "#475467", fontWeight: "600" },
  date: { fontSize: 12, color: "#98a2b3" },
  title: { fontSize: 20, fontWeight: "800", color: "#101828", lineHeight: 28 },
  hero: { alignItems: "center", marginVertical: 16 },
  sectionBlock: { marginTop: 16 },
  sectionTitle: { fontSize: 13, fontWeight: "700", color: "#667085", marginBottom: 4 },
  sectionBody: { fontSize: 15, color: "#1d2939", lineHeight: 22 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 16 },
  chip: { paddingHorizontal: 10, paddingVertical: 5, backgroundColor: "#eef0f3", borderRadius: 999 },
  chipAccent: { backgroundColor: "#eff4ff" },
  chipText: { fontSize: 12, color: "#475467" },
  chipTextAccent: { color: "#175cd3", fontWeight: "600" },
  primary: { marginTop: 24, backgroundColor: "#175cd3", borderRadius: 10, padding: 14, alignItems: "center" },
  primaryText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  secondary: {
    marginTop: 10,
    backgroundColor: "#fff",
    borderRadius: 10,
    padding: 14,
    alignItems: "center",
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: "#d0d5dd",
  },
  secondaryText: { color: "#344054", fontWeight: "600", fontSize: 15 },
});
