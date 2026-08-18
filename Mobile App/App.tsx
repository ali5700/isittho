import { StatusBar } from "expo-status-bar";
import { SafeAreaView, StyleSheet } from "react-native";

import CheckScreen from "./src/screens/CheckScreen";

export default function App() {
  return (
    <SafeAreaView style={styles.container}>
      <CheckScreen />
      <StatusBar style="auto" />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#fff",
  },
});
