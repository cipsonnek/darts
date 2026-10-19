import "leaflet/dist/leaflet.css";
import type { LatLngBoundsExpression, LatLngExpression } from "leaflet";
import { useEffect } from "react";
import { CircleMarker, MapContainer, Popup, TileLayer, useMap, useMapEvents } from "react-leaflet";
import { Link } from "react-router";
import { VENUE_KIND, zl, type VenueRow } from "./lib";

const POLAND: LatLngExpression = [52.07, 19.48];

function color(v: VenueRow): string {
  if (!v.active) return "#8b94a8";
  if (v.boards && v.boards_online < v.boards) return "#ef4f5f";
  if (v.alerts) return "#f5b942";
  return "#2ecc71";
}

function FitBounds({ points }: { points: [number, number][] }) {
  const map = useMap();
  const key = points.map((p) => p.join(",")).join(";");
  useEffect(() => {
    if (points.length === 1) map.setView(points[0], 13);
    else if (points.length > 1) map.fitBounds(points as LatLngBoundsExpression, { padding: [30, 30], maxZoom: 13 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return null;
}

/** OpenStreetMap with one dot per venue (green ok, yellow alerts, red board offline, grey inactive). */
export function VenueMap({ venues, className }: { venues: VenueRow[]; className?: string }) {
  const placed = venues.filter((v) => v.lat != null && v.lng != null);
  return (
    <MapContainer center={POLAND} zoom={6} className={className} scrollWheelZoom style={{ background: "var(--surface-2)" }}>
      <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      <FitBounds points={placed.map((v) => [v.lat!, v.lng!])} />
      {placed.map((v) => (
        <CircleMarker key={v.id} center={[v.lat!, v.lng!]} radius={9 + Math.min(6, v.boards * 2)}
          pathOptions={{ color: "#000", weight: 1.5, fillColor: color(v), fillOpacity: 0.9 }}>
          <Popup>
            <div style={{ minWidth: 180 }}>
              <div style={{ fontWeight: 700, fontSize: 14 }}>{v.name}</div>
              <div>{VENUE_KIND[v.kind] ?? v.kind} · {v.city}</div>
              <div>{v.address}</div>
              <div style={{ marginTop: 4 }}>Tarcze: {v.boards_online}/{v.boards} online · gry 30 dni: {v.games_30d}</div>
              <div>Przychód 30 dni: {zl(v.revenue_30d)}</div>
              <Link to={`/operator/venues/${v.id}`}>Szczegóły →</Link>
            </div>
          </Popup>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}

function ClickToPlace({ onPick }: { onPick: (lat: number, lng: number) => void }) {
  useMapEvents({ click: (e) => onPick(Number(e.latlng.lat.toFixed(5)), Number(e.latlng.lng.toFixed(5))) });
  return null;
}

function Recenter({ at }: { at: [number, number] | null }) {
  const map = useMap();
  useEffect(() => {
    if (at) map.setView(at, Math.max(map.getZoom(), 15));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [at?.[0], at?.[1]]);
  return null;
}

/** Small map for picking a venue's location by clicking. */
export function LocationPicker({ lat, lng, onPick, className }: {
  lat: number | null; lng: number | null; onPick: (lat: number, lng: number) => void; className?: string;
}) {
  const at: [number, number] | null = lat != null && lng != null ? [lat, lng] : null;
  return (
    <MapContainer center={at ?? POLAND} zoom={at ? 15 : 6} className={className} style={{ background: "var(--surface-2)" }}>
      <TileLayer attribution='&copy; OpenStreetMap' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      <ClickToPlace onPick={onPick} />
      <Recenter at={at} />
      {at && <CircleMarker center={at} radius={10} pathOptions={{ color: "#000", weight: 1.5, fillColor: "#e8324a", fillOpacity: 0.95 }} />}
    </MapContainer>
  );
}
