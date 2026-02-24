import * as fs from 'fs';
import ArrayBufferView = NodeJS.ArrayBufferView;

export const isFileOrDirectoryExists = async (path: string): Promise<boolean> => {
  try {
    const stat = await fs.promises.lstat(path);
    return stat.isFile() || stat.isDirectory();
  } catch {
    return false;
  }
};

export const getFilesInDir = (path: string): Promise<string[]> => {
  return new Promise((resolve, reject) => {
    fs.readdir(path, (err, files) => {
      if (err) reject(err);
      resolve(files);
    });
  });
};
