export type ReaderChoice = {
  choiceId: string;
  text: string;
  motive?: string;
  emotionalCost?: string;
  accessTier: 'free' | 'paid' | 'subscriber';
  priceHint?: number;
};

export type ReaderChapterView = {
  sessionId: string;
  worldId: string;
  worldVersionId: string;
  chapterId: string;
  chapterIndex: number;
  chapterTitle: string;
  recap?: string;
  body: string;
  relationshipHints?: string[];
  choices: ReaderChoice[];
  canContinue: boolean;
  paywall?: {
    required: boolean;
    reason?: string;
    quote?: number;
  };
};

export type WorldShelfCard = {
  worldId: string;
  title: string;
  subtitle?: string;
  genres: string[];
  riskRating: string;
  coverUrl?: string;
  trialAvailable: boolean;
  accessState: 'locked' | 'trial' | 'owned' | 'subscriber';
};
