import { StyleSheet, Text, View } from "react-native";
import type { Importance } from "@/types/article";

const COLORS: Record<string, string> = {
  A: "#d92d20",
  B: "#b54708",
  C: "#475467",
};

export function Badge({ importance }: { importance?: Importance }) {
  const key = importance ?? "C";
  return (
    <View style={[styles.badge, { backgroundColor: COLORS[key] ?? COLORS.C }]}>
      <Text style={styles.text}>{key}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    minWidth: 20,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 6,
    alignItems: "center",
  },
  text: { color: "#fff", fontSize: 12, fontWeight: "700" },
});
