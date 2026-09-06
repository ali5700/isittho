import { useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { ApiError, checkSituation } from "../api/client";
import type { CheckResponse } from "../api/types";
import SupportResourcesBanner from "../components/SupportResourcesBanner";
import { MAX_SITUATION_LENGTH, MIN_SITUATION_LENGTH } from "../constants";

const OUTCOME_COLORS: Record<string, string> = {
  red_flag: "#DC2626",
  yellow_flag: "#D97706",
  normal: "#16A34A",
};

// Display-only relabeling: the "normal" outcome value is shown to users as
// "Green Flag" to match the red/yellow/green flag framing. The underlying
// value stays "normal" everywhere else (API, breakdown keys, etc).
const LABEL_DISPLAY_OVERRIDES: Record<string, string> = {
  normal: "Green Flag",
};

function outcomeColor(label: string): string {
  return OUTCOME_COLORS[label] ?? "#374151";
}

function formatLabel(label: string): string {
  if (LABEL_DISPLAY_OVERRIDES[label]) return LABEL_DISPLAY_OVERRIDES[label];
  return label.replace(/_/g, " ");
}

export default function CheckScreen() {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CheckResponse | null>(null);

  const trimmedLength = text.trim().length;
  const canSubmit =
    trimmedLength >= MIN_SITUATION_LENGTH && trimmedLength <= MAX_SITUATION_LENGTH && !loading;

  async function handleSubmit() {
    if (!canSubmit) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const response = await checkSituation(text.trim());
      setResult(response);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  const verdictEntries = result ? Object.entries(result.verdict_breakdown) : [];
  const verdictTotal = verdictEntries.reduce((sum, [, count]) => sum + count, 0);

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView
        contentContainerStyle={styles.container}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={styles.title}>Is it tho?</Text>
        <Text style={styles.subtitle}>
          Describe a relationship situation and see how similar situations played out.
        </Text>

        <TextInput
          style={styles.input}
          multiline
          placeholder="What's going on? e.g. My partner read my texts without asking..."
          placeholderTextColor="#9CA3AF"
          value={text}
          onChangeText={setText}
          maxLength={MAX_SITUATION_LENGTH}
        />
        <Text style={styles.charCount}>
          {trimmedLength}/{MAX_SITUATION_LENGTH}
          {trimmedLength > 0 && trimmedLength < MIN_SITUATION_LENGTH
            ? ` — need at least ${MIN_SITUATION_LENGTH} characters`
            : ""}
        </Text>

        <Pressable
          style={[styles.button, !canSubmit && styles.buttonDisabled]}
          onPress={handleSubmit}
          disabled={!canSubmit}
        >
          {loading ? (
            <ActivityIndicator color="#FFFFFF" />
          ) : (
            <Text style={styles.buttonText}>Check</Text>
          )}
        </Pressable>

        {error && (
          <View style={styles.errorBox}>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        )}

        {result && (
          <View style={styles.results}>
            {result.needs_support_resources && <SupportResourcesBanner />}

            <Text style={styles.sectionTitle}>Verdict</Text>
            <View style={styles.verdictSummary}>
              <View
                style={[
                  styles.verdictDot,
                  { backgroundColor: outcomeColor(result.top_label) },
                ]}
              />
              <Text style={styles.verdictLabel}>{formatLabel(result.top_label)}</Text>
            </View>

            <View style={styles.breakdown}>
              {verdictEntries.map(([label, count]) => {
                const pct = verdictTotal > 0 ? count / verdictTotal : 0;
                return (
                  <View key={label} style={styles.breakdownRow}>
                    <Text style={styles.breakdownLabel}>{formatLabel(label)}</Text>
                    <View style={styles.breakdownBarTrack}>
                      <View
                        style={[
                          styles.breakdownBarFill,
                          {
                            width: `${Math.max(pct * 100, 4)}%`,
                            backgroundColor: outcomeColor(label),
                          },
                        ]}
                      />
                    </View>
                    <Text style={styles.breakdownCount}>{count}</Text>
                  </View>
                );
              })}
            </View>

            <Text style={styles.sectionTitle}>Similar situations</Text>
            {result.similar_submissions.map((item, idx) => (
              <View key={idx} style={styles.card}>
                <View style={styles.cardHeader}>
                  <Text style={styles.cardCategory}>{item.category}</Text>
                  <Text
                    style={[styles.cardOutcome, { color: outcomeColor(item.outcome_label) }]}
                  >
                    {formatLabel(item.outcome_label)}
                  </Text>
                </View>
                <Text style={styles.cardText}>{item.text_preview}</Text>
                <Text style={styles.cardSimilarity}>
                  {Math.round(item.similarity * 100)}% similar
                </Text>
              </View>
            ))}
          </View>
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  container: {
    padding: 20,
    paddingBottom: 48,
    backgroundColor: "#FFFFFF",
    flexGrow: 1,
  },
  title: { fontSize: 28, fontWeight: "700", color: "#111827" },
  subtitle: { fontSize: 15, color: "#6B7280", marginTop: 6, marginBottom: 20 },
  input: {
    minHeight: 110,
    borderWidth: 1,
    borderColor: "#D1D5DB",
    borderRadius: 12,
    padding: 14,
    fontSize: 16,
    color: "#111827",
    textAlignVertical: "top",
  },
  charCount: { fontSize: 12, color: "#9CA3AF", marginTop: 6, textAlign: "right" },
  button: {
    marginTop: 16,
    backgroundColor: "#111827",
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  buttonDisabled: { backgroundColor: "#D1D5DB" },
  buttonText: { color: "#FFFFFF", fontSize: 16, fontWeight: "600" },
  errorBox: {
    marginTop: 16,
    backgroundColor: "#FEF2F2",
    borderColor: "#FECACA",
    borderWidth: 1,
    borderRadius: 10,
    padding: 12,
  },
  errorText: { color: "#B91C1C", fontSize: 14 },
  results: { marginTop: 28 },
  sectionTitle: {
    fontSize: 13,
    fontWeight: "700",
    color: "#6B7280",
    textTransform: "uppercase",
    letterSpacing: 0.5,
    marginTop: 20,
    marginBottom: 10,
  },
  verdictSummary: { flexDirection: "row", alignItems: "center", gap: 8 },
  verdictDot: { width: 10, height: 10, borderRadius: 5 },
  verdictLabel: { fontSize: 18, fontWeight: "600", color: "#111827", textTransform: "capitalize" },
  breakdown: { marginTop: 12, gap: 8 },
  breakdownRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  breakdownLabel: { width: 90, fontSize: 13, color: "#374151", textTransform: "capitalize" },
  breakdownBarTrack: {
    flex: 1,
    height: 8,
    backgroundColor: "#F3F4F6",
    borderRadius: 4,
    overflow: "hidden",
  },
  breakdownBarFill: { height: 8, borderRadius: 4 },
  breakdownCount: { width: 24, fontSize: 13, color: "#6B7280", textAlign: "right" },
  card: {
    backgroundColor: "#F9FAFB",
    borderRadius: 12,
    padding: 14,
    marginBottom: 10,
  },
  cardHeader: { flexDirection: "row", justifyContent: "space-between", marginBottom: 6 },
  cardCategory: { fontSize: 12, color: "#6B7280", textTransform: "capitalize" },
  cardOutcome: { fontSize: 12, fontWeight: "700", textTransform: "capitalize" },
  cardText: { fontSize: 14, color: "#1F2937", lineHeight: 20 },
  cardSimilarity: { fontSize: 11, color: "#9CA3AF", marginTop: 8 },
});
