import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Where is my Seat",
    short_name: "WIMSeat",
    description: "Your train is full. Your journey isn't over.",
    start_url: "/",
    display: "standalone",
    background_color: "#efefef",
    theme_color: "#1b63a7",
    icons: [{ src: "/icon.svg", sizes: "any", type: "image/svg+xml" }],
  };
}
