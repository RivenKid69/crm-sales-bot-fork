import { sha1 } from '../utils/sha1';
import { md5 } from '../utils/md5';

export const generateToken = async (): Promise<any> => {
  const crypto = await import('crypto');
  return new Promise((resolve, reject) => {
    crypto.randomBytes(16, (err, buf) => {
      if (err) reject(err);
      resolve(sha1(buf));
    });
  });
};

export const generateDeviceCode = async (maxId: number, applicationName: string): Promise<string> => {
  return md5(String(maxId + 1)) + sha1(String(maxId + 1) + applicationName);
};
