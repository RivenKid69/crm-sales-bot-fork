import { HttpException } from '@nestjs/common';
import { md5 } from '../utils/md5';
import * as path from 'path';
import * as fs from 'fs';
import validateImage from './validate-image';
// import * as sharp from 'sharp';
import * as uniqid from 'uniqid';
import * as substr from 'locutus/php/strings/substr';

export const saveBase64ImageExif = async (base64: string, subDirectory: string): Promise<string> => {
  return '';
  // const data = Buffer.from(base64, 'base64');
  // if (!data) throw new HttpException('Received photo is not in base64', 422);
  //
  // const fileName = md5(uniqid()) + '.jpg';
  // const formattedFileName = md5(uniqid()) + '.jpg';
  // const imageDir = substr(fileName, 0, 2);
  // const fullPath = path.resolve('static', 'images', subDirectory, imageDir);
  // await fs.promises.mkdir(fullPath, { recursive: true });
  // const pathToFile = path.join(fullPath, fileName);
  // await fs.promises.writeFile(pathToFile, data);
  // const isImage = validateImage(pathToFile);
  // if (!isImage) {
  //   await fs.promises.unlink(pathToFile);
  //   throw new HttpException('Received photo is not image', 422);
  // }
  //
  // const newPathToFile = path.join(fullPath, formattedFileName);
  // try {
  //   await sharp(pathToFile).toFormat('jpeg', { mozjpeg: true }).jpeg({ quality: 80 }).toFile(newPathToFile);
  // } catch (e) {
  //   throw new HttpException("Can't save processed image on server", 500);
  // }
  // await fs.promises.unlink(pathToFile); // Тут мы удаляем не обработанный вариант фотографии (напрямую менять не обработанное изображение нельзя)
  // return path.join(subDirectory, imageDir, formattedFileName);
};
