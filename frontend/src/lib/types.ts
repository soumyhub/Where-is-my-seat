import { z } from "zod";

/* Runtime schemas for everything the API returns. Responses are validated before use
   so a backend/frontend mismatch shows a clear error instead of a broken screen. */

export const StatusSchema = z.enum(["CONFIRMED", "RAC", "WAITLISTED", "UNAVAILABLE", "UNKNOWN"]);
export const OverallStatusSchema = z.enum([
  "CONFIRMED",
  "RAC",
  "WAITLISTED",
  "UNAVAILABLE",
  "UNKNOWN",
  "UNRESERVED",
]);

const StationRefSchema = z.object({ code: z.string(), name: z.string(), city: z.string() });

export const PlaceSchema = z.object({
  kind: z.enum(["station", "city"]),
  key: z.string(),
  code: z.string().nullable(),
  name: z.string(),
  subtitle: z.string(),
  city: z.string(),
  codes: z.array(z.string()),
  served: z.boolean().default(true), // false: no timetable train stops here
});

export const AvailabilitySchema = z.object({
  status: StatusSchema,
  count: z.number().nullable(),
  label: z.string(),
  display: z.string(),
  source: z.string(),
  observed_at: z.string(),
  is_live: z.boolean(),
  is_simulated: z.boolean(),
  stale: z.boolean(),
  note: z.string().nullable(),
});

const TicketSchema = z.object({
  kind: z.enum(["reserved", "unreserved"]),
  train_number: z.string(),
  from_station: StationRefSchema,
  to_station: StationRefSchema,
  journey_date: z.string(),
  travel_class: z.string(),
  class_label: z.string(),
  quota: z.string(),
  strategy: z.enum(["standard", "book_beyond", "upstream_boarding", "split", "later_boarding"]),
  class_mismatch: z.boolean(),
  distance_km: z.number(),
  availability: AvailabilitySchema.nullable(),
  fare: z.object({ per_person: z.number(), total: z.number(), is_estimate: z.boolean(), basis: z.string() }),
  booking: z.object({ channel: z.string(), url: z.string().nullable(), bookable: z.boolean(), note: z.string() }),
});

const StopSchema = z.object({
  code: z.string(),
  name: z.string(),
  arr: z.string().nullable(),
  dep: z.string().nullable(),
  km: z.number(),
  day: z.number(),
  role: z.enum(["board", "alight", "halt"]),
});

const TrainSchema = z.object({
  number: z.string(),
  name: z.string(),
  category: z.string(),
  runs_on: z.string(),
  classes: z.array(z.string()),
  unreserved: z.boolean(),
  superfast: z.boolean(),
  simulated: z.boolean(),
  source: z.string(),
  notes: z.array(z.string()),
  start_date: z.string().nullish(), // the day this run leaves its first station
});

const LegSchema = z.object({
  kind: z.enum(["train", "road"]),
  purpose: z.enum(["ride", "feeder", "transfer", "onward"]),
  from_station: StationRefSchema,
  to_station: StationRefSchema,
  depart_at: z.string(),
  arrive_at: z.string(),
  duration_minutes: z.number(),
  day_change: z.number(),
  distance_km: z.number(),
  train: TrainSchema.nullable(),
  road: z.object({ mode: z.string(), km: z.number(), cost_per_person: z.number(), basis: z.string() }).nullable(),
  tickets: z.array(TicketSchema),
  stops: z.array(StopSchema),
  buffer_before_minutes: z.number().nullable(),
  instructions: z.array(z.string()),
  cost_per_person: z.number(),
  class_fares: z.record(z.string(), z.number()),
});

const IdeaSchema = z.object({
  strategy: z.enum(["book_beyond", "upstream_boarding", "split", "later_boarding"]),
  title: z.string(),
  detail: z.string(),
  tickets: z.array(TicketSchema),
  extra_road: z.record(z.string(), z.unknown()).nullable(),
});

export const ItinerarySchema = z.object({
  id: z.string(),
  categories: z.array(z.string()),
  primary_category: z.string(),
  headline: z.string(),
  legs: z.array(LegSchema),
  depart_at: z.string(),
  arrive_at: z.string(),
  total_minutes: z.number(),
  travel_date: z.string(),
  date_offset: z.number(),
  passengers: z.number(),
  cost_per_person: z.number(),
  cost_total: z.number(),
  transfers: z.number(),
  train_changes: z.number(),
  tickets_count: z.number(),
  reserved_tickets_count: z.number(),
  separate_tickets: z.boolean(),
  single_train: z.boolean(),
  overall_status: OverallStatusSchema,
  availability_score: z.number(),
  convenience_score: z.number(),
  score: z.number(),
  connection_quality: z.enum(["none", "comfortable", "tight", "long_wait"]),
  why: z.array(z.string()),
  fits: z.array(z.string()),
  warnings: z.array(z.string()),
  tips: z.array(z.string()),
  booking_tip: z.string().nullable(),
  vs_preferred: z
    .object({
      extra_cost_per_person: z.number(),
      extra_minutes: z.number(),
      arrival_delta_minutes: z.number(),
    })
    .nullable(),
  ideas: z.array(IdeaSchema),
  contains_simulated: z.boolean(),
  contains_estimates: z.boolean(),
});

export const DataNoticeSchema = z.object({
  mode: z.enum(["demo", "timetable", "live"]),
  label: z.string(),
  details: z.array(z.string()),
  timetable_source: z.string(),
  timetable_version: z.string(),
  timetable_updated: z.string(),
  timetable_simulated: z.boolean(),
  availability_source: z.string(),
  availability_live: z.boolean(),
  availability_simulated: z.boolean(),
  fare_basis: z.string(),
  coverage: z.string(),
  provider_note: z.string().nullable(),
  live_checks: z.boolean().default(false), // single tickets can be checked live
  live_checks_source: z.string().nullish(),
});

export const LiveUsageSchema = z.object({
  available: z.boolean(),
  source: z.string().nullable(),
  monthly_limit: z.number().nullable(),
  used_this_month: z.number().nullable(),
  remaining_this_month: z.number().nullable(),
  blocked_reason: z.string().nullish(),
  tools: z.boolean().default(false), // live tools (running status, station board, fare…) are set up
  requests_used: z.number().nullish(),
  requests_left: z.number().nullish(),
});
export type LiveUsage = z.infer<typeof LiveUsageSchema>;

export const AvailabilityCheckResponseSchema = z.object({
  results: z.array(
    z.object({
      request: z.object({
        train_number: z.string(),
        journey_date: z.string(),
        from_code: z.string(),
        to_code: z.string(),
        travel_class: z.string(),
      }),
      ok: z.boolean(),
      error: z.string().nullable(),
      availability: AvailabilitySchema.nullable(),
    }),
  ),
  data_notice: DataNoticeSchema,
  checked_at: z.string(),
  live_usage: LiveUsageSchema,
});
export type AvailabilityCheckResponse = z.infer<typeof AvailabilityCheckResponseSchema>;
export type TicketCheckInput = AvailabilityCheckResponse["results"][number]["request"];

export const SearchResponseSchema = z.object({
  query: z.object({
    origin: PlaceSchema,
    destination: PlaceSchema,
    date: z.string(),
    passengers: z.number(),
    travel_class: z.string(),
    max_budget: z.number().nullable(),
    max_duration_hours: z.number().nullable(),
    max_transfers: z.number(),
    flexible_days: z.number(),
    include_nearby: z.boolean(),
    allow_unreserved: z.boolean(),
    smart_tickets: z.boolean(),
    sort: z.string(),
  }),
  data_notice: DataNoticeSchema,
  summary: z.object({
    headline: z.string(),
    subline: z.string(),
    direct_count: z.number(),
    direct_confirmed: z.number(),
    alternatives_with_seats: z.number(),
    best_bookable_id: z.string().nullable(),
    preferred_id: z.string().nullable(),
  }),
  preferred: ItinerarySchema.nullable(),
  itineraries: z.array(ItinerarySchema),
  date_strip: z
    .array(
      z.object({
        date: z.string(),
        label: z.string(),
        best_status: OverallStatusSchema.nullable(),
        options: z.number(),
        bookable_options: z.number(),
        cheapest_bookable: z.number().nullable(),
      }),
    )
    .nullable(),
  rush: z
    .object({ level: z.string(), festival: z.string(), festival_date: z.string(), message: z.string() })
    .nullable(),
  hidden: z.record(z.string(), z.number()),
  no_results_reason: z.string().nullable(),
  no_results_message: z.string().nullable(),
  search_stats: z.record(z.string(), z.unknown()),
  generated_at: z.string(),
});

export const JourneyResponseSchema = z.object({
  itinerary: ItinerarySchema,
  origin: PlaceSchema,
  destination: PlaceSchema,
  data_notice: DataNoticeSchema,
  checked_at: z.string(),
});

export const MetaSchema = z.object({
  app: z.string(),
  version: z.string(),
  today: z.string(),
  demo_date: z.string(),
  max_advance_days: z.number(),
  classes: z.array(z.object({ code: z.string(), label: z.string() })),
  samples: z.array(
    z.object({
      id: z.string(),
      title: z.string(),
      description: z.string(),
      shows: z.array(z.string()),
      from_name: z.string(),
      to_name: z.string(),
      request: z.record(z.string(), z.unknown()),
    }),
  ),
  data_notice: DataNoticeSchema,
  rush_periods: z.array(
    z.object({ name: z.string(), date: z.string(), from: z.string(), to: z.string(), level: z.string() }),
  ),
  limits: z.record(z.string(), z.unknown()),
});

export const ApiErrorBodySchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    hint: z.string().nullish(),
    details: z.unknown().optional(),
  }),
});

export const TRAVEL_CLASSES = ["SL", "3A", "2A", "1A", "CC", "2S", "ANY"] as const;
export const SORT_MODES = ["best", "cheapest", "fastest", "fewest_transfers"] as const;

export const SearchRequestSchema = z
  .object({
    origin: z.string().min(2, "Choose where you start from"),
    destination: z.string().min(2, "Choose where you are going"),
    date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Pick a travel date"),
    passengers: z.number().int().min(1, "At least 1 traveller").max(6, "At most 6 travellers per booking"),
    travel_class: z.enum(TRAVEL_CLASSES),
    max_budget: z.number().int().min(50, "Budget must be at least ₹50").max(100000).nullable(),
    max_duration_hours: z.number().min(1).max(48).nullable(),
    max_transfers: z.number().int().min(0).max(3),
    flexible_days: z.number().int().min(0).max(3),
    include_nearby: z.boolean(),
    allow_unreserved: z.boolean(),
    smart_tickets: z.boolean(),
    sort: z.enum(SORT_MODES),
  })
  .refine((v) => v.origin !== v.destination, {
    message: "From and To must be different places",
    path: ["destination"],
  });

export type Status = z.infer<typeof StatusSchema>;
export type OverallStatus = z.infer<typeof OverallStatusSchema>;
export type Place = z.infer<typeof PlaceSchema>;
export type Availability = z.infer<typeof AvailabilitySchema>;
export type Itinerary = z.infer<typeof ItinerarySchema>;
export type Leg = Itinerary["legs"][number];
export type Ticket = Leg["tickets"][number];
export type Idea = Itinerary["ideas"][number];
export type DataNotice = z.infer<typeof DataNoticeSchema>;
export type SearchResponse = z.infer<typeof SearchResponseSchema>;
export type JourneyResponse = z.infer<typeof JourneyResponseSchema>;
export type Meta = z.infer<typeof MetaSchema>;
export type SearchRequest = z.infer<typeof SearchRequestSchema>;
export type TravelClass = (typeof TRAVEL_CLASSES)[number];
export type SortMode = (typeof SORT_MODES)[number];

export const JourneyMapSchema = z.object({
  legs: z.array(
    z.object({
      kind: z.enum(["train", "road"]),
      train_number: z.string().nullable(),
      train_name: z.string().nullable(),
      segments: z.array(z.object({ points: z.array(z.tuple([z.number(), z.number()])), matched: z.boolean() })),
      stops: z.array(
        z.object({
          code: z.string(),
          name: z.string(),
          lat: z.number(),
          lon: z.number(),
          role: z.enum(["board", "alight", "halt", "road"]),
        }),
      ),
    }),
  ),
  bounds: z.array(z.tuple([z.number(), z.number()])).nullable(),
  track_share: z.number(),
  attribution: z.string(),
  available: z.boolean(),
});
export type JourneyMap = z.infer<typeof JourneyMapSchema>;

/* ----- live tools (RailRadar free plan) ----- */

const live = <T extends z.ZodType>(data: T) =>
  z.object({ data, source: z.string(), fetched_at: z.string(), cached: z.boolean(), requests_left: z.number() });
const Ref = z.object({ code: z.string().nullable(), name: z.string().nullable() });

export const LiveTrainSchema = live(
  z.object({
    train_number: z.string().nullable(),
    train_name: z.string().nullable(),
    start_date: z.string().nullable(),
    status: z.string().nullable(),
    is_live: z.boolean(),
    tracking_mode: z.string().nullable(),
    delay_minutes: z.number().nullable(),
    last_updated_at: z.string().nullable(),
    current: Ref.extend({ status: z.string().nullable(), speed_kmh: z.number().nullable() }).nullable(),
    previous_halt: Ref.nullable(),
    next_halt: Ref.nullable(),
    alerts: z.array(z.string()),
    halts: z.array(
      z.object({
        code: z.string().nullable(),
        name: z.string().nullable(),
        scheduled_arrival: z.string().nullable(),
        scheduled_departure: z.string().nullable(),
        actual_arrival: z.string().nullable(),
        actual_departure: z.string().nullable(),
        delay_minutes: z.number().nullable(),
        platform: z.string().nullable(),
        status: z.string().nullable(),
      }),
    ),
  }),
);
export type LiveTrain = z.infer<typeof LiveTrainSchema>;

export const StationBoardSchema = live(
  z.object({
    station: Ref,
    window: z.object({ from: z.string(), to: z.string() }).partial().nullable(),
    trains: z.array(
      z.object({
        number: z.string().nullable(),
        name: z.string().nullable(),
        type: z.string().nullable(),
        from: z.string().nullable(),
        to: z.string().nullable(),
        arrival: z.string().nullable(),
        departure: z.string().nullable(),
        platform: z.string().nullable(),
        state: z.string().nullable(),
        expected_arrival: z.string().nullable(),
        expected_departure: z.string().nullable(),
        delay_minutes: z.number().nullable(),
      }),
    ),
  }),
);
export type StationBoard = z.infer<typeof StationBoardSchema>;

export const LiveFareSchema = live(
  z.object({
    total: z.number().nullable(),
    distance_km: z.number().nullable(),
    parts: z.record(z.string(), z.number()),
    class: z.string(),
    quota: z.string(),
  }),
);
export type LiveFare = z.infer<typeof LiveFareSchema>;

export const CoachesSchema = live(
  z.object({
    station: Ref.extend({ platform: z.string().nullable() }),
    reversal: z.boolean(),
    coaches: z.array(
      z.object({
        position: z.number().nullable(),
        code: z.string().nullable(),
        class: z.string().nullable(),
        name: z.string().nullable(),
      }),
    ),
  }),
);
export type Coaches = z.infer<typeof CoachesSchema>;

export const PunctualitySchema = live(
  z.object({
    average_arrival_delay: z.number().nullable(),
    average_departure_delay: z.number().nullable(),
    on_time_percent: z.number().nullable(),
    worst: z.object({ code: z.string().nullable(), name: z.string().nullable(), delay: z.number().nullable() }).nullable(),
    halts: z.array(
      z.object({
        code: z.string().nullable(),
        name: z.string().nullable(),
        arrival_delay: z.number().nullable(),
        departure_delay: z.number().nullable(),
      }),
    ),
  }),
);
export type Punctuality = z.infer<typeof PunctualitySchema>;

export const AlertsSchema = live(
  z.object({
    items: z.array(z.object({ start_date: z.string().nullable(), type: z.string().nullable(), message: z.string() })),
    updated_at: z.string().nullable(),
  }),
);
export type Alerts = z.infer<typeof AlertsSchema>;
