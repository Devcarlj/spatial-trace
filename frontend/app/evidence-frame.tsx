"use client";

import Image from "next/image";
import { useState } from "react";

export type MaskOverlay = {
  data_url: string;
  bbox: number[];
  width: number;
  height: number;
};

type Props = {
  src: string;
  box?: number[] | null;
  mask?: MaskOverlay | null;
  uncertain: boolean;
};

export default function EvidenceFrame({ src, box, mask, uncertain }: Props) {
  const [size, setSize] = useState<number[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [showMask, setShowMask] = useState(true);
  const [showBox, setShowBox] = useState(true);
  const [zoom, setZoom] = useState(false);
  return <div>
    <div className="frame-tools" aria-label="Evidence display controls">
      <button type="button" aria-pressed={showMask} disabled={!mask} onClick={() => setShowMask(!showMask)}>Pixel mask</button>
      <button type="button" aria-pressed={showBox} disabled={!box} onClick={() => setShowBox(!showBox)}>Object box</button>
      <button type="button" aria-pressed={zoom} onClick={() => setZoom(!zoom)}>Zoom {zoom ? "200%" : "100%"}</button>
      {!mask && <span>Pixel mask unavailable · box evidence only</span>}
    </div>
    {failed ? <p role="alert" className="error">This saved frame is unavailable. Re-index the source using a new clip name.</p> :
      <div className="frame-scroll" tabIndex={zoom ? 0 : undefined} aria-label={zoom ? "Zoomed frame; scroll to inspect" : undefined}>
        <div className="frame" style={{ width: zoom ? "200%" : "100%" }}>
          <Image unoptimized width={768} height={576} src={src} alt="Selected historical video observation"
            onLoad={event => setSize([event.currentTarget.naturalWidth, event.currentTarget.naturalHeight])}
            onError={() => setFailed(true)} />
          {size && <svg className="overlay" viewBox={`0 0 ${size[0]} ${size[1]}`} aria-label="Detected object overlay">
            {showMask && mask && <image data-testid="pixel-mask" href={mask.data_url}
              x={mask.bbox[0]} y={mask.bbox[1]} width={mask.bbox[2] - mask.bbox[0]} height={mask.bbox[3] - mask.bbox[1]}
              preserveAspectRatio="none" style={{ imageRendering: "pixelated" }} />}
            {showBox && box && <rect x={box[0]} y={box[1]} width={box[2] - box[0]} height={box[3] - box[1]}
              fill="none" stroke={uncertain ? "#edbd5e" : "#a8ec87"} strokeWidth="3" vectorEffect="non-scaling-stroke"
              strokeDasharray={uncertain ? "8 5" : undefined} />}
          </svg>}
        </div>
      </div>}
  </div>;
}
