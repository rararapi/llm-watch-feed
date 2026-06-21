import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";

const queryClient = new QueryClient();

export default function RootLayout() {
  return (
    <QueryClientProvider client={queryClient}>
      <SafeAreaProvider>
        <StatusBar style="dark" />
        <Stack
          screenOptions={{
            headerStyle: { backgroundColor: "#fff" },
            headerTitleStyle: { fontSize: 16 },
          }}
        >
          <Stack.Screen name="index" options={{ title: "AI News Watch" }} />
          <Stack.Screen name="article/[id]" options={{ title: "記事", headerBackTitle: "一覧" }} />
          <Stack.Screen name="subscribe" options={{ title: "購読 (RSS)" }} />
        </Stack>
      </SafeAreaProvider>
    </QueryClientProvider>
  );
}
