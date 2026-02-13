import { motion, AnimatePresence } from "framer-motion";
import { useReducedMotion } from "@/hooks/useReducedMotion";

interface Props {
  badgeName: string;
  badgeEmoji: string;
  show: boolean;
  onClose: () => void;
}

export function BadgeCelebration({ badgeName, badgeEmoji, show, onClose }: Props) {
  const reduced = useReducedMotion();

  return (
    <AnimatePresence>
      {show && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        >
          <motion.div
            className="bg-card rounded-2xl shadow-2xl p-8 text-center max-w-xs"
            initial={reduced ? {} : { scale: 0.5, opacity: 0 }}
            animate={reduced ? {} : { scale: 1, opacity: 1 }}
            exit={reduced ? {} : { scale: 0.8, opacity: 0 }}
            transition={{ type: "spring", bounce: 0.4 }}
            onClick={(e) => e.stopPropagation()}
          >
            <motion.div
              className="text-6xl mb-3"
              initial={reduced ? {} : { scale: 0, rotate: -180 }}
              animate={reduced ? {} : { scale: 1, rotate: 0 }}
              transition={{ type: "spring", bounce: 0.6, delay: 0.2 }}
            >
              {badgeEmoji}
            </motion.div>
            <h3 className="text-lg font-bold mb-1">Badge Earned!</h3>
            <p className="text-sm text-muted-foreground">{badgeName}</p>
            <button
              type="button"
              onClick={onClose}
              className="mt-4 px-4 py-2 text-sm bg-primary text-primary-foreground rounded-md hover:opacity-90"
            >
              Awesome!
            </button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
