import { useRef, useState } from "react";
import {
  Animated,
  Easing,
  LayoutChangeEvent,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";

// Roughly 3 lines at cardText's fontSize/lineHeight below — the collapsed
// "peek" height before a card becomes expandable.
const COLLAPSED_HEIGHT = 20 * 3;

interface Props {
  category: string;
  outcomeLabel: string;
  outcomeColor: string;
  text: string;
  similarity: number;
}

export default function SimilarSituationCard({
  category,
  outcomeLabel,
  outcomeColor,
  text,
  similarity,
}: Props) {
  const [expanded, setExpanded] = useState(false);
  const [naturalHeight, setNaturalHeight] = useState<number | null>(null);
  const animatedHeight = useRef(new Animated.Value(COLLAPSED_HEIGHT)).current;
  const hasInteracted = useRef(false);

  const isExpandable = naturalHeight !== null && naturalHeight > COLLAPSED_HEIGHT + 1;

  function handleTextLayout(e: LayoutChangeEvent) {
    const height = e.nativeEvent.layout.height;
    if (height === naturalHeight) return;
    setNaturalHeight(height);
    // Before the user has toggled anything, keep the resting (collapsed)
    // height in sync with reality — text that's short enough to need no
    // truncation should sit at its real height, not leave empty space.
    // Once the user has interacted, leave the animation alone so a stray
    // re-layout can't fight an in-flight or completed toggle.
    if (!hasInteracted.current && height <= COLLAPSED_HEIGHT) {
      animatedHeight.setValue(height);
    }
  }

  function toggle() {
    if (!isExpandable) return;
    hasInteracted.current = true;
    Animated.timing(animatedHeight, {
      toValue: expanded ? COLLAPSED_HEIGHT : (naturalHeight ?? COLLAPSED_HEIGHT),
      duration: 250,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: false,
    }).start();
    setExpanded(!expanded);
  }

  return (
    <Pressable
      onPress={toggle}
      disabled={!isExpandable}
      style={({ pressed }) => [styles.card, pressed && isExpandable && styles.cardPressed]}
    >
      <View style={styles.cardHeader}>
        <Text style={styles.cardCategory}>{category}</Text>
        <Text style={[styles.cardOutcome, { color: outcomeColor }]}>{outcomeLabel}</Text>
      </View>

      <Animated.View style={{ height: animatedHeight, overflow: "hidden" }}>
        <Text style={styles.cardText} onLayout={handleTextLayout}>
          {text}
        </Text>
      </Animated.View>

      <View style={styles.cardFooter}>
        <Text style={styles.cardSimilarity}>{Math.round(similarity * 100)}% similar</Text>
        {isExpandable && (
          <Text style={styles.cardToggle}>{expanded ? "Show less ▴" : "Read more ▾"}</Text>
        )}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: "#F9FAFB",
    borderRadius: 12,
    padding: 14,
    marginBottom: 10,
  },
  cardPressed: { backgroundColor: "#F3F4F6" },
  cardHeader: { flexDirection: "row", justifyContent: "space-between", marginBottom: 6 },
  cardCategory: { fontSize: 12, color: "#6B7280", textTransform: "capitalize" },
  cardOutcome: { fontSize: 12, fontWeight: "700", textTransform: "capitalize" },
  cardText: { fontSize: 14, color: "#1F2937", lineHeight: 20 },
  cardFooter: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginTop: 8,
  },
  cardSimilarity: { fontSize: 11, color: "#9CA3AF" },
  cardToggle: { fontSize: 12, fontWeight: "600", color: "#2563EB" },
});
