import { Linking, StyleSheet, Text, View } from "react-native";

// Shown whenever an API response's needs_support_resources flag is true,
// on both the Check and Submit screens. Calm, non-alarming styling —
// this is informational, not a warning.
export default function SupportResourcesBanner() {
  return (
    <View style={styles.banner}>
      <Text style={styles.text}>
        If you need to talk to someone: 1800RESPECT — call{" "}
        <Text style={styles.link} onPress={() => Linking.openURL("tel:1800737732")}>
          1800 737 732
        </Text>{" "}
        or text{" "}
        <Text style={styles.link} onPress={() => Linking.openURL("sms:0458737732")}>
          0458 737 732
        </Text>
        , available 24/7. More info at{" "}
        <Text style={styles.link} onPress={() => Linking.openURL("https://www.1800respect.org.au")}>
          1800RESPECT.org.au
        </Text>
        .
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    backgroundColor: "#EFF6FF",
    borderColor: "#BFDBFE",
    borderWidth: 1,
    borderRadius: 12,
    padding: 16,
    marginBottom: 8,
  },
  text: { fontSize: 13, color: "#1E3A8A", lineHeight: 20 },
  link: { fontWeight: "700", textDecorationLine: "underline" },
});
