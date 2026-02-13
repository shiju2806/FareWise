import { create } from "zustand";

interface SearchState {
  isSearching: boolean;
  sliderValue: number;
  setIsSearching: (v: boolean) => void;
  setSliderValue: (v: number) => void;
}

export const useSearchStore = create<SearchState>((set) => ({
  isSearching: false,
  sliderValue: 40,
  setIsSearching: (v) => set({ isSearching: v }),
  setSliderValue: (v) => set({ sliderValue: v }),
}));
