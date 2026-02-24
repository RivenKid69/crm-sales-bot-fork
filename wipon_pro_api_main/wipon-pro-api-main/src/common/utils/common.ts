import * as fs from 'fs';
import * as substr from 'locutus/php/strings/substr';

export const httpBuildQuery = (o: any): string => {
  return new URLSearchParams(o).toString();
};

export const sleep = (secs: number) => {
  return new Promise((res, rej) => {
    setTimeout(() => {
      res(true);
    }, secs * 1000);
  });
};

export const getPrefixForDeletedDeviceCode = (userId: number | null, deviceCode: string): string => {
  const formattedDate = new Intl.DateTimeFormat('ru-RU', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date());
  return `EXPIRED_${userId}_${formattedDate}_${deviceCode}`;
};

export const hex2bin = (s: string) => {
  const ret: any = [];
  let i = 0;
  let l;
  s += '';
  for (l = s.length; i < l; i += 2) {
    const c = parseInt(substr(s, i, 1), 16);
    const k = parseInt(substr(s, i + 1, 1), 16);
    if (isNaN(c) || isNaN(k)) return false;
    ret.push((c << 4) | k);
  }
  // eslint-disable-next-line prefer-spread
  return String.fromCharCode.apply(String, ret);
};

export const fileGetContents = (url: string) => {
  return fs.readFileSync(url, 'utf-8');
};

export const paginate = (data: any, total: number, currentPage: number, perPage: number, fullUrl: string) => {
  const page = currentPage || 1;
  const from = page === 1 ? 1 : (page - 1) * perPage + 1;
  const to = page * perPage;
  let last_page = Math.ceil(total / perPage);
  if (total === 0) last_page = 1;
  const prev_page_url = page === 1 ? null : `${fullUrl}?page=${page - 1}`;
  const next_page_url = last_page === page ? null : `${fullUrl}?page=${page + 1}`;

  return {
    total,
    per_page: perPage,
    current_page: page,
    last_page,
    from,
    to,
    prev_page_url,
    next_page_url,
    data,
  };
};
