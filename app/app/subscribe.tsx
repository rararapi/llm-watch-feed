import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import * as Clipboard from "expo-clipboard";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { FEEDS_BASE } from "@/lib/config";

// Mirrors generate_feeds.py FEED_CONFIGS. Push notifications are out of scope (Phase 2).
const FEEDS: { file: string; name: string; description: string }[] = [
  { file: "all.xml", name: "All", description: "重要度AまたはBのAIニュース" },
  { file: "major-models.xml", name: "Major Models", description: "重要度Aの主要モデル情報" },
  { file: "pricing.xml", name: "Pricing", description: "価格・コスト関連" },
  { file: "open-models.xml", name: "Open Models", description: "オープンウェイトモデル" },
  { file: "coding.xml", name: "Coding", description: "コーディング性能特化" },
  { file: "multimodal.xml", name: "Multimodal", description: "マルチモーダル・音声・動画" },
];

export default function SubscribeScreen() {
  const insets = useSafeAreaInsets();
  const [copied, setCopied] = useState<string | null>(null);

  const copy = async (file: string) => {
    const url = `${FEEDS_BASE}/${file}`;
    await Clipboard.setStringAsync(url);
    setCopied(file);
    setTimeout(() => setCopied((c) => (c === file ? null : c)), 1400);
  };

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={{ padding: 16, paddingBottom: insets.bottom + 24 }}
    >
      <Text style={styles.intro}>
        お好みのRSSリーダーに以下のフィードURLを登録してください。
      </Text>
      {FEEDS.map((f) => (
        <View key={f.file} style={styles.row}>
          <View style={styles.info}>
            <Text style={styles.name}>{f.name}</Text>
            <Text style={styles.desc}>{f.description}</Text>
            <Text style={styles.url} numberOfLines={1}>
              {`${FEEDS_BASE}/${f.file}`}
            </Text>
          </View>
          <Pressable style={styles.copy} onPress={() => copy(f.file)}>
            <Text style={styles.copyText}>{copied === f.file ? "コピー済み" : "コピー"}</Text>
          </Pressable>
        </View>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { backgroundColor: "#f5f6f8" },
  intro: { fontSize: 14, color: "#475467", marginBottom: 12, lineHeight: 20 },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    backgroundColor: "#fff",
    borderRadius: 12,
    padding: 12,
    marginBottom: 10,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: "#e4e7ec",
  },
  info: { flex: 1, gap: 2 },
  name: { fontSize: 15, fontWeight: "700", color: "#101828" },
  desc: { fontSize: 12, color: "#667085" },
  url: { fontSize: 11, color: "#98a2b3", marginTop: 2 },
  copy: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: "#eff4ff",
    borderRadius: 8,
  },
  copyText: { color: "#175cd3", fontWeight: "600", fontSize: 13 },
});
