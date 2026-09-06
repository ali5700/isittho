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

import { ApiError, submitSituation } from "../api/client";
import type { SubmitResponse } from "../api/types";
import SupportResourcesBanner from "../components/SupportResourcesBanner";
import { MAX_SITUATION_LENGTH, MIN_SITUATION_LENGTH } from "../constants";

export default function SubmitScreen() {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SubmitResponse | null>(null);

  const trimmedLength = text.trim().length;
  const canSubmit =
    trimmedLength >= MIN_SITUATION_LENGTH && trimmedLength <= MAX_SITUATION_LENGTH && !loading;

  async function handleSubmit() {
    if (!canSubmit) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const response = await submitSituation(text.trim());
      setResult(response);
      setText("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView
        contentContainerStyle={styles.container}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={styles.title}>Share your story</Text>
        <Text style={styles.subtitle}>
          Describe a relationship situation you've been through. It may help someone else going
          through something similar.
        </Text>

        <TextInput
          style={styles.input}
          multiline
          placeholder="What happened? e.g. My partner read my texts without asking..."
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
            <Text style={styles.buttonText}>Share</Text>
          )}
        </Pressable>

        {error && (
          <View style={styles.errorBox}>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        )}

        {result && (
          <View style={styles.results}>
            <View style={styles.successBox}>
              <Text style={styles.successText}>{result.message}</Text>
            </View>
            {result.needs_support_resources && <SupportResourcesBanner />}
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
  successBox: {
    backgroundColor: "#F0FDF4",
    borderColor: "#BBF7D0",
    borderWidth: 1,
    borderRadius: 10,
    padding: 14,
    marginBottom: 8,
  },
  successText: { color: "#166534", fontSize: 14, lineHeight: 20 },
});
