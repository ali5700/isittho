import { useState } from "react";
import { StatusBar } from "expo-status-bar";
import { Pressable, SafeAreaView, StyleSheet, Text, View } from "react-native";

import CheckScreen from "./src/screens/CheckScreen";
import SubmitScreen from "./src/screens/SubmitScreen";

type Tab = "check" | "submit";

export default function App() {
  const [tab, setTab] = useState<Tab>("check");

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.tabBar}>
        <TabButton label="Check" active={tab === "check"} onPress={() => setTab("check")} />
        <TabButton
          label="Share your story"
          active={tab === "submit"}
          onPress={() => setTab("submit")}
        />
      </View>

      {/* Both screens stay mounted so switching tabs doesn't lose in-progress input or results. */}
      <View style={[styles.screen, tab !== "check" && styles.hidden]}>
        <CheckScreen />
      </View>
      <View style={[styles.screen, tab !== "submit" && styles.hidden]}>
        <SubmitScreen />
      </View>

      <StatusBar style="auto" />
    </SafeAreaView>
  );
}

function TabButton({
  label,
  active,
  onPress,
}: {
  label: string;
  active: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable style={[styles.tabButton, active && styles.tabButtonActive]} onPress={onPress}>
      <Text style={[styles.tabButtonText, active && styles.tabButtonTextActive]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#fff",
  },
  tabBar: {
    flexDirection: "row",
    paddingHorizontal: 20,
    paddingTop: 12,
    gap: 8,
    borderBottomWidth: 1,
    borderBottomColor: "#F3F4F6",
  },
  tabButton: {
    paddingVertical: 10,
    paddingHorizontal: 4,
    borderBottomWidth: 2,
    borderBottomColor: "transparent",
  },
  tabButtonActive: { borderBottomColor: "#111827" },
  tabButtonText: { fontSize: 14, fontWeight: "600", color: "#9CA3AF" },
  tabButtonTextActive: { color: "#111827" },
  screen: { flex: 1 },
  hidden: { display: "none" },
});
