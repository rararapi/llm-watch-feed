import { useState } from "react";
import {
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import type { Importance } from "@/types/article";
import type { FilterState } from "@/lib/filter";

const IMPORTANCE_OPTIONS: { key: Importance | "all"; label: string }[] = [
  { key: "all", label: "すべて" },
  { key: "A", label: "重要度A" },
  { key: "B", label: "B" },
];

export function Filters({
  state,
  sources,
  resultCount,
  onChange,
}: {
  state: FilterState;
  sources: string[];
  resultCount: number;
  onChange: (next: FilterState) => void;
}) {
  const [sourceOpen, setSourceOpen] = useState(false);

  return (
    <View style={styles.wrap}>
      <TextInput
        style={styles.search}
        placeholder="キーワードで絞り込み"
        placeholderTextColor="#98a2b3"
        value={state.query}
        onChangeText={(query) => onChange({ ...state, query })}
        autoCorrect={false}
      />
      <View style={styles.row}>
        <View style={styles.segmented}>
          {IMPORTANCE_OPTIONS.map((opt) => {
            const active = state.importance === opt.key;
            return (
              <Pressable
                key={opt.key}
                style={[styles.seg, active && styles.segActive]}
                onPress={() => onChange({ ...state, importance: opt.key })}
              >
                <Text style={[styles.segText, active && styles.segTextActive]}>{opt.label}</Text>
              </Pressable>
            );
          })}
        </View>
        <Pressable style={styles.sourceBtn} onPress={() => setSourceOpen(true)}>
          <Text style={styles.sourceBtnText} numberOfLines={1}>
            {state.source === "all" ? "全ソース" : state.source}
          </Text>
        </Pressable>
      </View>
      <Text style={styles.count}>{resultCount}件</Text>

      <Modal visible={sourceOpen} animationType="slide" transparent>
        <Pressable style={styles.backdrop} onPress={() => setSourceOpen(false)}>
          <View style={styles.sheet}>
            <Text style={styles.sheetTitle}>ソースで絞り込み</Text>
            <ScrollView>
              {["all", ...sources].map((s) => (
                <Pressable
                  key={s}
                  style={styles.sheetItem}
                  onPress={() => {
                    onChange({ ...state, source: s });
                    setSourceOpen(false);
                  }}
                >
                  <Text style={styles.sheetItemText}>{s === "all" ? "全ソース" : s}</Text>
                </Pressable>
              ))}
            </ScrollView>
          </View>
        </Pressable>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 8, paddingBottom: 8 },
  search: {
    backgroundColor: "#fff",
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: "#d0d5dd",
    fontSize: 14,
  },
  row: { flexDirection: "row", gap: 8, alignItems: "center" },
  segmented: {
    flexDirection: "row",
    backgroundColor: "#eef0f3",
    borderRadius: 10,
    padding: 2,
    flex: 1,
  },
  seg: { flex: 1, paddingVertical: 6, alignItems: "center", borderRadius: 8 },
  segActive: { backgroundColor: "#fff" },
  segText: { fontSize: 13, color: "#475467" },
  segTextActive: { color: "#101828", fontWeight: "700" },
  sourceBtn: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: "#fff",
    borderRadius: 10,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: "#d0d5dd",
    maxWidth: 140,
  },
  sourceBtnText: { fontSize: 13, color: "#344054" },
  count: { fontSize: 12, color: "#98a2b3" },
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.3)", justifyContent: "flex-end" },
  sheet: {
    backgroundColor: "#fff",
    borderTopLeftRadius: 16,
    borderTopRightRadius: 16,
    padding: 16,
    maxHeight: "70%",
  },
  sheetTitle: { fontSize: 15, fontWeight: "700", marginBottom: 8, color: "#101828" },
  sheetItem: { paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: "#eaecf0" },
  sheetItemText: { fontSize: 14, color: "#344054" },
});
