import { useState } from "react";
import { Image, StyleSheet, Text, View } from "react-native";
import type { Article } from "@/types/article";
import { thumbUrl } from "@/lib/thumb";
import { sourceColors } from "@/lib/meta";

// AI image → OG image → color placeholder (with source initials). If the image fails
// to load, fall back to the placeholder — same priority as the web.
export function Thumbnail({ a, size = 64 }: { a: Article; size?: number }) {
  const [failed, setFailed] = useState(false);
  const url = thumbUrl(a);
  const [c1, c2] = sourceColors(a.source);
  const label = (a.source || a.provider || "AI").slice(0, 2).toUpperCase();

  if (url && !failed) {
    return (
      <Image
        source={{ uri: url }}
        style={[styles.box, { width: size, height: size }]}
        onError={() => setFailed(true)}
      />
    );
  }
  return (
    <View style={[styles.box, styles.ph, { width: size, height: size, backgroundColor: c1, borderColor: c2 }]}>
      <Text style={styles.phText}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  box: { borderRadius: 10, backgroundColor: "#eee" },
  ph: { alignItems: "center", justifyContent: "center", borderWidth: 2 },
  phText: { color: "#fff", fontWeight: "800", fontSize: 16 },
});
