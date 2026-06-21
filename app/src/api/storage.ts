// Offline cache of the last successfully fetched articles, in AsyncStorage
// (Expo Go compatible; no dev build needed).
import AsyncStorage from "@react-native-async-storage/async-storage";
import type { Article } from "@/types/article";

const KEY = "articles.cache.v1";

export async function saveArticles(articles: Article[]): Promise<void> {
  try {
    await AsyncStorage.setItem(KEY, JSON.stringify(articles));
  } catch {
    // Cache write failures must never break the app.
  }
}

export async function loadArticles(): Promise<Article[] | null> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Article[]) : null;
  } catch {
    return null;
  }
}
