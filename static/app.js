const canvas = document.getElementById("cardCanvas");
const ctx = canvas.getContext("2d");
const urlInput = document.getElementById("tweetUrl");
const generateBtn = document.getElementById("generateBtn");
const downloadBtn = document.getElementById("downloadBtn");
const message = document.getElementById("message");
const staticPreview = document.getElementById("staticPreview");

const CARD_WIDTH = 980;
const FONT_STACK =
  '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Arial Unicode MS", Arial, sans-serif';
const X_LOGO_PATH =
  "M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z";
const STAT_ICON_PATHS = {
  reply:
    "M1.751 10c0-4.42 3.584-8 8.005-8h4.366c4.49 0 8.129 3.64 8.129 8.129 0 2.96-1.607 5.68-4.196 7.11l-8.054 4.46v-3.69h-.067c-4.49.1-8.183-3.51-8.183-8.01zm8.005-6c-3.317 0-6.005 2.69-6.005 6.005 0 3.37 2.77 6.08 6.138 6.005l.351-.008h1.761v2.3l5.087-2.81c1.951-1.08 3.163-3.13 3.163-5.36 0-3.39-2.744-6.132-6.129-6.132H9.756z",
  retweet:
    "M4.5 3.88l4.432 4.14-1.364 1.46L5.5 7.55V16c0 1.1.896 2 2 2H13v2H7.5c-2.209 0-4-1.79-4-4V7.55L1.432 9.48.068 8.02 4.5 3.88zM16.5 6H11V4h5.5c2.209 0 4 1.79 4 4v8.45l2.068-1.93 1.364 1.46-4.432 4.14-4.432-4.14 1.364-1.46 2.068 1.93V8c0-1.1-.896-2-2-2z",
  like:
    "M16.697 5.5c-1.222-.06-2.679.51-3.89 2.16l-.805 1.09-.806-1.09C9.984 6.01 8.526 5.44 7.304 5.5c-1.243.07-2.349.78-2.91 1.91-.552 1.12-.633 2.78.479 4.82 1.074 1.97 3.257 4.27 7.129 6.61 3.87-2.34 6.052-4.64 7.126-6.61 1.111-2.04 1.03-3.7.477-4.82-.561-1.13-1.666-1.84-2.908-1.91zm4.187 7.69c-1.351 2.48-4.001 5.12-8.379 7.67l-.503.3-.504-.3c-4.379-2.55-7.029-5.19-8.382-7.67-1.36-2.5-1.41-4.86-.514-6.67.887-1.79 2.647-2.91 4.601-3.01 1.651-.09 3.368.56 4.798 2.01 1.429-1.45 3.146-2.1 4.798-2.01 1.954.1 3.714 1.22 4.601 3.01.896 1.81.846 4.17-.514 6.67z",
};
const QUOTE_MEDIA_GAP = 36;
const MAX_SINGLE_PHOTO_HEIGHT = 2200;
const VERIFIED_BADGE_GAP = 20;
const sampleTweet = {
  text:
    "工信部将开展AI+软件专项行动\n\n这件事在去年12月的中央经济工作会议的时候已经预定了。\n当时也给大家展开说了。\n\nAI的机会巨大，如果能有机会介入任何一个央企的AI转型，都足够小公司吃好几年了。",
  author: {
    name: "RobinSeun_维京黑船",
    handle: "RobinSeun",
    avatar: "",
    verified: true,
  },
  date_label: "Apr 29, 2026",
  stats: {
    replies: "11",
    retweets: "1",
    likes: "37",
    views: "6.5K",
  },
  images: [
    {
      placeholder: true,
      title: "工信部将开展 “人工智能+软件” 专项行动\n国产AI应用或迎投资机遇",
      source: "财联社",
      date: "2026-04-29 08:02",
    },
  ],
};

function setMessage(text, isError = false) {
  message.textContent = text;
  message.classList.toggle("is-error", isError);
}

function proxyUrl(url) {
  if (!url) return "";
  return `/api/proxy-image?url=${encodeURIComponent(url)}`;
}

function font(size, weight = 400, family = FONT_STACK) {
  return `${weight} ${size}px ${family}`;
}

function hasCjk(text) {
  return /[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]/.test(text);
}

function textProfile(text) {
  if (hasCjk(text)) {
    return { size: 31, lineHeight: 40 };
  }
  if (/[\u0600-\u06ff\u0590-\u05ff]/.test(text)) {
    return { size: 29, lineHeight: 42 };
  }
  return { size: 28, lineHeight: 38 };
}

function tokenizeText(text) {
  const cjk = /[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]/;
  const tokens = [];
  let current = "";

  for (const char of Array.from(text)) {
    if (char === "\n") {
      if (current) tokens.push(current);
      current = "";
      tokens.push("\n");
    } else if (cjk.test(char)) {
      if (current) tokens.push(current);
      current = "";
      tokens.push(char);
    } else if (/\s/.test(char)) {
      current += char;
      tokens.push(current);
      current = "";
    } else {
      current += char;
    }
  }
  if (current) tokens.push(current);
  return tokens;
}

function wrapText(context, text, maxWidth) {
  const tokens = tokenizeText(text);
  const lines = [];
  let line = "";

  for (const token of tokens) {
    if (token === "\n") {
      lines.push(line.trimEnd());
      line = "";
      continue;
    }

    const candidate = line + token;
    if (context.measureText(candidate).width <= maxWidth) {
      line = candidate;
      continue;
    }

    if (line) {
      lines.push(line.trimEnd());
      line = token.trimStart();
      continue;
    }

    let fragment = "";
    for (const char of Array.from(token)) {
      const next = fragment + char;
      if (context.measureText(next).width > maxWidth && fragment) {
        lines.push(fragment);
        fragment = char;
      } else {
        fragment = next;
      }
    }
    line = fragment;
  }

  if (line || lines.length === 0) lines.push(line.trimEnd());
  return lines;
}

function roundRectPath(context, x, y, width, height, radius) {
  const r = Math.min(radius, width / 2, height / 2);
  context.beginPath();
  context.moveTo(x + r, y);
  context.arcTo(x + width, y, x + width, y + height, r);
  context.arcTo(x + width, y + height, x, y + height, r);
  context.arcTo(x, y + height, x, y, r);
  context.arcTo(x, y, x + width, y, r);
  context.closePath();
}

function drawRoundRect(context, x, y, width, height, radius, fill, stroke, lineWidth = 1) {
  roundRectPath(context, x, y, width, height, radius);
  if (fill) {
    context.fillStyle = fill;
    context.fill();
  }
  if (stroke) {
    context.strokeStyle = stroke;
    context.lineWidth = lineWidth;
    context.stroke();
  }
}

function drawVerified(context, x, y, size, color = "#1d9bf0") {
  context.save();
  context.translate(x, y);
  context.fillStyle = color;
  context.beginPath();
  const points = 16;
  for (let i = 0; i < points; i += 1) {
    const angle = (Math.PI * 2 * i) / points - Math.PI / 2;
    const radius = i % 2 === 0 ? size / 2 : size * 0.42;
    const px = Math.cos(angle) * radius;
    const py = Math.sin(angle) * radius;
    if (i === 0) context.moveTo(px, py);
    else context.lineTo(px, py);
  }
  context.closePath();
  context.fill();
  context.strokeStyle = "#fff";
  context.lineWidth = Math.max(2.4, size * 0.09);
  context.lineCap = "round";
  context.lineJoin = "round";
  context.beginPath();
  context.moveTo(-size * 0.2, 0);
  context.lineTo(-size * 0.05, size * 0.16);
  context.lineTo(size * 0.24, -size * 0.18);
  context.stroke();
  context.restore();
}

function drawFallbackAvatar(context, x, y, size, name) {
  const initials = Array.from((name || "X").trim()).slice(0, 2).join("").toUpperCase();
  const grad = context.createLinearGradient(x, y, x + size, y + size);
  grad.addColorStop(0, "#e9eff2");
  grad.addColorStop(1, "#cbd8df");
  context.fillStyle = grad;
  context.beginPath();
  context.arc(x + size / 2, y + size / 2, size / 2, 0, Math.PI * 2);
  context.fill();
  context.fillStyle = "#15211c";
  context.font = font(size * 0.34, 800);
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.fillText(initials, x + size / 2, y + size / 2 + 1);
}

function loadImage(src) {
  return new Promise((resolve) => {
    if (!src) {
      resolve(null);
      return;
    }
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => resolve(null);
    image.src = src;
  });
}

async function loadAssets(tweet) {
  const avatar = await loadImage(proxyUrl(tweet.author?.avatar));
  const images = [];
  for (const item of tweet.images || []) {
    if (item.placeholder) {
      images.push(null);
    } else {
      images.push(await loadImage(proxyUrl(item.url)));
    }
  }
  const quote = tweet.quote ? await loadAssets(tweet.quote) : null;
  return { avatar, images, quote };
}

function drawAvatar(context, image, x, y, size, name) {
  context.save();
  context.beginPath();
  context.arc(x + size / 2, y + size / 2, size / 2, 0, Math.PI * 2);
  context.clip();
  if (image) {
    const scale = Math.max(size / image.width, size / image.height);
    const width = image.width * scale;
    const height = image.height * scale;
    context.drawImage(image, x + (size - width) / 2, y + (size - height) / 2, width, height);
  } else {
    context.restore();
    drawFallbackAvatar(context, x, y, size, name);
    return;
  }
  context.restore();
}

function drawSvgPath(context, pathData, x, y, size, color, viewBox = 24) {
  context.save();
  context.translate(x, y);
  context.scale(size / viewBox, size / viewBox);
  context.fillStyle = color;
  context.fill(new Path2D(pathData));
  context.restore();
}

function drawXLogo(context, x, y) {
  const size = 59;
  drawSvgPath(context, X_LOGO_PATH, x - size / 2, y - size / 2, size, "#0f1b16");
}

function drawInlineVerified(context, textX, textWidth, baselineY, size, color) {
  drawVerified(context, textX + textWidth + VERIFIED_BADGE_GAP + size / 2, baselineY - 11, size, color);
}

function drawStatIcon(context, type, x, y, color) {
  drawSvgPath(context, STAT_ICON_PATHS[type], x, y, 40, color);
}

function drawMediaPlaceholder(context, item, x, y, width) {
  const height = 294;
  drawRoundRect(context, x, y, width, height, 18, "#ffffff", "#d1dee5", 2);
  context.save();
  roundRectPath(context, x + 1, y + 1, width - 2, height - 2, 17);
  context.clip();
  const grad = context.createLinearGradient(x, y, x, y + height);
  grad.addColorStop(0, "#ffffff");
  grad.addColorStop(1, "#f8fafb");
  context.fillStyle = grad;
  context.fillRect(x, y, width, height);

  context.fillStyle = "#000000";
  context.font = font(40, 850, '"Arial Unicode MS", "PingFang SC", Arial, sans-serif');
  context.textBaseline = "top";
  const lines = wrapText(context, item.title || "帖子图片", width - 40).slice(0, 3);
  let cursor = y + 58;
  for (const line of lines) {
    context.fillText(line, x + 20, cursor);
    cursor += 54;
  }

  context.fillStyle = "#e70022";
  context.beginPath();
  context.arc(x + 42, y + height - 67, 20, 0, Math.PI * 2);
  context.fill();
  context.fillStyle = "#fff";
  context.font = font(28, 850, "Arial, sans-serif");
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.fillText("C", x + 42, y + height - 67);
  context.textAlign = "left";
  context.fillStyle = "#485766";
  context.font = font(18, 700);
  context.fillText(item.source || "图片来源", x + 72, y + height - 78);
  context.fillStyle = "#a2adb7";
  context.font = font(15, 500);
  context.fillText(item.date || "", x + 72, y + height - 50);
  context.restore();
  return height;
}

function drawImageCover(context, image, x, y, width, height, radius) {
  drawRoundRect(context, x, y, width, height, radius, "#f1f5f7", "#d1dee5", 2);
  context.save();
  roundRectPath(context, x + 1, y + 1, width - 2, height - 2, radius - 1);
  context.clip();
  if (image) {
    const scale = Math.max(width / image.width, height / image.height);
    const drawWidth = image.width * scale;
    const drawHeight = image.height * scale;
    context.drawImage(image, x + (width - drawWidth) / 2, y + (height - drawHeight) / 2, drawWidth, drawHeight);
  }
  context.restore();
}

function drawImageContain(context, image, x, y, width, height, radius) {
  drawRoundRect(context, x, y, width, height, radius, "#f1f5f7", "#d1dee5", 2);
  context.save();
  roundRectPath(context, x + 1, y + 1, width - 2, height - 2, radius - 1);
  context.clip();
  if (image) {
    const scale = Math.min(width / image.width, height / image.height);
    const drawWidth = image.width * scale;
    const drawHeight = image.height * scale;
    context.drawImage(image, x + (width - drawWidth) / 2, y + (height - drawHeight) / 2, drawWidth, drawHeight);
  }
  context.restore();
}

function drawImageCoverRaw(context, image, x, y, width, height) {
  context.fillStyle = "#f1f5f7";
  context.fillRect(x, y, width, height);
  if (!image) return;
  const scale = Math.max(width / image.width, height / image.height);
  const drawWidth = image.width * scale;
  const drawHeight = image.height * scale;
  context.drawImage(image, x + (width - drawWidth) / 2, y + (height - drawHeight) / 2, drawWidth, drawHeight);
}

function drawImageContainRaw(context, image, x, y, width, height) {
  context.fillStyle = "#f1f5f7";
  context.fillRect(x, y, width, height);
  if (!image) return;
  const scale = Math.min(width / image.width, height / image.height);
  const drawWidth = image.width * scale;
  const drawHeight = image.height * scale;
  context.drawImage(image, x + (width - drawWidth) / 2, y + (height - drawHeight) / 2, drawWidth, drawHeight);
}

function isVideoMedia(item = {}) {
  return item.type === "video" || item.type === "gif";
}

function formatDuration(seconds) {
  if (!Number.isFinite(Number(seconds))) return "";
  const total = Math.max(0, Math.round(Number(seconds)));
  const minutes = Math.floor(total / 60);
  const remainder = String(total % 60).padStart(2, "0");
  return `${minutes}:${remainder}`;
}

function drawVideoOverlay(context, item, x, y, width, height) {
  context.save();
  const centerX = x + width / 2;
  const centerY = y + height / 2;
  context.fillStyle = "rgba(0, 0, 0, 0.52)";
  context.beginPath();
  context.arc(centerX, centerY, 44, 0, Math.PI * 2);
  context.fill();
  context.strokeStyle = "#ffffff";
  context.lineWidth = 5;
  context.lineJoin = "round";
  context.beginPath();
  context.moveTo(centerX - 13, centerY - 21);
  context.lineTo(centerX - 13, centerY + 21);
  context.lineTo(centerX + 24, centerY);
  context.closePath();
  context.stroke();

  const duration = formatDuration(item?.duration);
  if (duration) {
    context.font = font(22, 800);
    const badgeWidth = context.measureText(duration).width + 22;
    drawRoundRect(context, x + 18, y + height - 52, badgeWidth, 36, 6, "rgba(0, 0, 0, 0.78)");
    context.fillStyle = "#ffffff";
    context.textAlign = "left";
    context.textBaseline = "middle";
    context.fillText(duration, x + 29, y + height - 34);
  }
  context.restore();
}

function drawQuoteMedia(context, items, images, x, y, width, height) {
  const count = Math.min(items.length, 4);
  if (!count) return 0;

  context.save();
  context.beginPath();
  context.rect(x, y, width, height);
  context.clip();
  context.fillStyle = "#f1f5f7";
  context.fillRect(x, y, width, height);

  if (count === 1) {
    if (isVideoMedia(items[0])) {
      drawImageCoverRaw(context, images[0], x, y, width, height);
      drawVideoOverlay(context, items[0], x, y, width, height);
    } else {
      drawImageContainRaw(context, images[0], x, y, width, height);
    }
  } else {
    const gap = 4;
    const cellW = (width - gap) / 2;
    const cellH = count <= 2 ? height : (height - gap) / 2;
    for (let i = 0; i < count; i += 1) {
      const col = i % 2;
      const row = Math.floor(i / 2);
      const px = x + col * (cellW + gap);
      const py = y + row * (cellH + gap);
      drawImageCoverRaw(context, images[i], px, py, cellW, cellH);
      if (isVideoMedia(items[i])) {
        drawVideoOverlay(context, items[i], px, py, cellW, cellH);
      }
    }
    context.fillStyle = "#ffffff";
    context.fillRect(x + cellW, y, gap, height);
    if (count > 2) {
      context.fillRect(x, y + cellH, width, gap);
    }
  }

  context.restore();
  return height;
}

function measureMediaHeight(items = [], images = [], width, variant = "main") {
  const count = Math.min(items.length, 4);
  if (!count) return 0;
  if (count === 1) {
    const item = items[0];
    if (item.placeholder) return 294;
    const image = images[0];
    const rawRatio = item.width && item.height ? item.height / item.width : image ? image.height / image.width : 0.56;
    const maxHeight = isVideoMedia(item) ? (variant === "quote" ? width : 520) : MAX_SINGLE_PHOTO_HEIGHT;
    return Math.max(250, Math.min(maxHeight, width * rawRatio));
  }
  if (variant === "quote") {
    return Math.max(360, Math.min(620, width * 0.68));
  }
  return count <= 2 ? 280 : 448;
}

function mediaLayout(items, images, x, y, width, variant = "main") {
  const count = Math.min(items.length, 4);
  if (!count) return 0;

  if (count === 1) {
    const item = items[0];
    if (item.placeholder) {
      return drawMediaPlaceholder(ctx, item, x, y, width);
    }
    const image = images[0];
    const height = measureMediaHeight(items, images, width, variant);
    if (variant === "quote") {
      drawQuoteMedia(ctx, items, images, x, y, width, height);
      return height;
    }
    if (isVideoMedia(item)) {
      drawImageCover(ctx, image, x, y, width, height, 18);
      drawVideoOverlay(ctx, item, x, y, width, height);
    } else {
      drawImageContain(ctx, image, x, y, width, height, 18);
    }
    return height;
  }

  const gap = variant === "quote" ? 4 : 8;
  const cellW = (width - gap) / 2;
  const totalHeight = measureMediaHeight(items, images, width, variant);
  if (variant === "quote") {
    return drawQuoteMedia(ctx, items, images, x, y, width, totalHeight);
  }
  const cellH = count <= 2 ? totalHeight : (totalHeight - gap) / 2;
  for (let i = 0; i < count; i += 1) {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const px = x + col * (cellW + gap);
    const py = y + row * (cellH + gap);
    if (variant === "quote") {
      drawImageCoverRaw(ctx, images[i], px, py, cellW, cellH);
      if (isVideoMedia(items[i])) {
        drawVideoOverlay(ctx, items[i], px, py, cellW, cellH);
      }
    } else {
      drawImageCover(ctx, images[i], px, py, cellW, cellH, 14);
      if (isVideoMedia(items[i])) {
        drawVideoOverlay(ctx, items[i], px, py, cellW, cellH);
      }
    }
  }
  return totalHeight;
}

function shortDateLabel(label = "") {
  return label.replace(/,\s*\d{4}$/, "");
}

function verifiedColor(author = {}) {
  return author.verification_type === "organization" ? "#f4c430" : "#1d9bf0";
}

function measureQuoteCard(quote, quoteAssets, width) {
  if (!quote) return 0;
  const padding = 24;
  const profile = textProfile(quote.text || "");
  const lineHeight = Math.max(36, profile.lineHeight - 2);
  ctx.font = font(Math.max(28, profile.size - 1), 420);
  const lines = wrapText(ctx, quote.text || "", width - padding * 2);
  const mediaHeight = measureMediaHeight(quote.images || [], quoteAssets?.images || [], width, "quote");
  const mediaGap = mediaHeight ? QUOTE_MEDIA_GAP : 0;
  return padding + 48 + 24 + lines.length * lineHeight + mediaGap + mediaHeight + (mediaHeight ? 0 : padding);
}

function drawQuoteCard(context, quote, quoteAssets, x, y, width) {
  const height = measureQuoteCard(quote, quoteAssets, width);
  const padding = 24;
  const radius = 20;
  drawRoundRect(context, x, y, width, height, radius, "#ffffff", "#d1dee5", 2);

  context.save();
  roundRectPath(context, x + 1, y + 1, width - 2, height - 2, radius - 1);
  context.clip();

  const author = quote.author || {};
  const avatarSize = 56;
  const headerY = y + padding;
  drawAvatar(context, quoteAssets?.avatar, x + padding, headerY, avatarSize, author.name);

  context.textAlign = "left";
  context.textBaseline = "alphabetic";
  context.font = font(31, 800);
  context.fillStyle = "#0f1b16";
  const nameX = x + padding + avatarSize + 12;
  const nameY = headerY + 32;
  let name = author.name || "X User";
  const maxNameWidth = width - padding * 2 - avatarSize - 280;
  while (context.measureText(name).width > maxNameWidth && name.length > 3) {
    name = `${name.slice(0, -2)}…`;
  }
  context.fillText(name, nameX, nameY);
  const nameWidth = context.measureText(name).width;
  let metaX = nameX + nameWidth + 16;
  if (author.verified) {
    drawInlineVerified(context, nameX, nameWidth, nameY, 31, verifiedColor(author));
    metaX += VERIFIED_BADGE_GAP + 31;
  }
  context.font = font(31, 440);
  context.fillStyle = "#536372";
  context.fillText(`@${author.handle || "user"} · ${shortDateLabel(quote.date_label || "")}`, metaX, nameY);

  const profile = textProfile(quote.text || "");
  const textSize = Math.max(28, profile.size - 1);
  const lineHeight = Math.max(36, profile.lineHeight - 2);
  context.font = font(textSize, 420);
  context.fillStyle = "#111b16";
  context.textBaseline = "top";
  const lines = wrapText(context, quote.text || "", width - padding * 2);
  let cursor = y + padding + 48 + 24;
  for (const line of lines) {
    context.fillText(line, x + padding, cursor);
    cursor += lineHeight;
  }

  if ((quote.images || []).length) {
    cursor += QUOTE_MEDIA_GAP;
    mediaLayout(quote.images, quoteAssets?.images || [], x, cursor, width, "quote");
  }

  context.restore();
  return height;
}

function getVisibleStats(stats = {}) {
  return [
    ["reply", stats.replies],
    ["retweet", stats.retweets],
    ["like", stats.likes],
  ].filter(([, value]) => value !== undefined && value !== null && value !== "");
}

async function renderCard(tweet) {
  staticPreview.classList.add("is-hidden");
  canvas.classList.remove("is-hidden");
  const assets = await loadAssets(tweet);
  const ratio = Math.max(1, window.devicePixelRatio || 1);
  const paddingX = 62;
  const maxTextWidth = CARD_WIDTH - paddingX * 2;
  const author = tweet.author || {};
  const profile = textProfile(tweet.text || "");

  ctx.font = font(profile.size, 420);
  const textLines = wrapText(ctx, tweet.text || "", maxTextWidth);
  const textHeight = textLines.length * profile.lineHeight;
  const mediaTopGap = (tweet.images || []).length ? 28 : 0;
  const measuredMediaHeight = measureMediaHeight(tweet.images || [], assets.images || [], maxTextWidth);
  const quoteTopGap = tweet.quote ? 28 : 0;
  const measuredQuoteHeight = measureQuoteCard(tweet.quote, assets.quote, maxTextWidth);

  const contentTop = 176;
  const footerHeight = 74;
  const cardHeight = Math.ceil(
    contentTop + textHeight + mediaTopGap + measuredMediaHeight + quoteTopGap + measuredQuoteHeight + footerHeight + 40,
  );
  canvas.width = Math.round(CARD_WIDTH * ratio);
  canvas.height = Math.round(cardHeight * ratio);
  canvas.style.width = `min(100%, ${CARD_WIDTH}px)`;
  canvas.style.height = "auto";
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, CARD_WIDTH, cardHeight);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, CARD_WIDTH, cardHeight);

  const avatarSize = 90;
  const avatarY = 58;
  const headerTextX = paddingX + avatarSize + 14;
  drawAvatar(ctx, assets.avatar, paddingX, avatarY, avatarSize, author.name);

  ctx.textBaseline = "alphabetic";
  ctx.textAlign = "left";
  ctx.font = font(31, 800);
  ctx.fillStyle = "#0f1b16";
  const nameY = 94;
  let fittedName = author.name || "X User";
  const maxNameWidth = CARD_WIDTH - paddingX * 2 - avatarSize - 160;
  while (ctx.measureText(fittedName).width > maxNameWidth && fittedName.length > 3) {
    fittedName = `${fittedName.slice(0, -2)}…`;
  }
  ctx.fillText(fittedName, headerTextX, nameY);
  const nameWidth = ctx.measureText(fittedName).width;
  if (author.verified) {
    drawInlineVerified(ctx, headerTextX, nameWidth, nameY, 31, verifiedColor(author));
  }

  ctx.font = font(31, 440);
  ctx.fillStyle = "#536372";
  ctx.fillText(`@${author.handle || "user"}`, headerTextX, 132);
  drawXLogo(ctx, CARD_WIDTH - 94, 104);

  ctx.font = font(profile.size, 420);
  ctx.fillStyle = "#111b16";
  ctx.textBaseline = "top";
  let y = contentTop;
  for (const line of textLines) {
    ctx.fillText(line, paddingX, y);
    y += profile.lineHeight;
  }

  if ((tweet.images || []).length) {
    y += mediaTopGap;
    y += mediaLayout(tweet.images, assets.images, paddingX, y, maxTextWidth);
  }

  if (tweet.quote) {
    y += quoteTopGap;
    y += drawQuoteCard(ctx, tweet.quote, assets.quote, paddingX, y, maxTextWidth);
  }

  const footerY = cardHeight - 65;
  const statColor = "#536372";
  let statX = paddingX;
  ctx.font = font(29, 440);
  ctx.textBaseline = "middle";
  const statOffsets = { reply: 50, retweet: 50, like: 50 };
  for (const [type, value] of getVisibleStats(tweet.stats)) {
    drawStatIcon(ctx, type, statX, footerY - 20, statColor);
    ctx.fillStyle = statColor;
    const textX = statX + statOffsets[type];
    ctx.fillText(String(value), textX, footerY);
    statX = textX + ctx.measureText(String(value)).width + 32;
  }

  const views = tweet.stats?.views;
  const dateText = tweet.date_label || "";
  if (dateText || views) {
    ctx.textAlign = "right";
    let rightX = CARD_WIDTH - paddingX;
    if (views) {
      const viewsText = `${views} Views`;
      ctx.font = font(28, 820);
      ctx.fillStyle = "#0f1b16";
      ctx.fillText(viewsText, rightX, footerY);
      rightX -= ctx.measureText(viewsText).width;
      ctx.font = font(28, 450);
      ctx.fillStyle = statColor;
      ctx.fillText(`${dateText} · `, rightX, footerY);
    } else {
      ctx.font = font(28, 450);
      ctx.fillStyle = statColor;
      ctx.fillText(dateText, rightX, footerY);
    }
    ctx.textAlign = "left";
  }

  downloadBtn.disabled = false;
}

async function fetchTweet(url) {
  const response = await fetch("/api/tweet", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  const payload = await response.json();
  if (!response.ok || !payload.ok) {
    throw new Error(payload.error || "抓取失败。");
  }
  return payload.tweet;
}

generateBtn.addEventListener("click", async () => {
  const url = urlInput.value.trim();
  if (!url) {
    setMessage("请先粘贴一条 X 帖子链接。", true);
    return;
  }
  generateBtn.disabled = true;
  downloadBtn.disabled = true;
  setMessage("正在抓取帖子并生成图片…");
  try {
    const tweet = await fetchTweet(url);
    await renderCard(tweet);
    const warning = tweet.warnings?.length ? "部分来源抓取失败，已使用可用数据生成。" : "";
    setMessage(warning || "生成好了，可以下载 PNG。");
  } catch (error) {
    setMessage(error.message, true);
  } finally {
    generateBtn.disabled = false;
  }
});

downloadBtn.addEventListener("click", () => {
  const link = document.createElement("a");
  link.download = `x-share-card-${Date.now()}.png`;
  link.href = canvas.toDataURL("image/png");
  link.click();
});

urlInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    generateBtn.click();
  }
});

setMessage("粘贴 X 帖子链接后生成分享图。");
