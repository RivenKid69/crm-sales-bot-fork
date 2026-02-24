import { ForbiddenException, HttpException, Injectable, NotFoundException } from '@nestjs/common';
import { GetUsersChecksDto } from '../dto/get-users-check.dto';
import { InjectRepository } from '@nestjs/typeorm';
import { ChecksRepository } from '../data/checks.repository';
import { getNowAlmatyTime, getStartOfMonth } from '../../../common/helpers/datetime';
import { ValidateCheckDataDto } from '../dto/validate-check-data.dto';
import { HttpService } from '@nestjs/axios';
import { FindOrCreateItemUseCase } from '../../items/domain/use-cases/find-or-create-item.use-case';
import appConfig from '../../../config/app.config';
import { BfAuthenticityService } from '../../bf-authenticity/bf-authenticity.service';
import { CountItemByExciseCodeUseCase } from '../../items/domain/use-cases/count-item-by-excise-code.use-case';
import { SetItemAndProductRelationUseCase } from '../../items/domain/use-cases/set-item-and-product-relation.use-case';
import { DisassociateItemFromProductUseCase } from '../../items/domain/use-cases/disassociate-item-from-product.use-case';
import { getManager } from 'typeorm';
import { CheckDao } from '../../../common/dao/check.dao';
import { FindUsersStoreUseCase } from '../../stores/domain/use-cases/find-users-store.use-case';
import { StoreChecksPictureDto } from '../dto/store-checks-picture.dto';
import { saveBase64ImageExif } from '../../../common/helpers/save-image';
import * as fs from 'fs';
import * as path from 'path';
import { getFilesInDir, isFileOrDirectoryExists } from '../../../common/helpers/fs';
import { ItemDao } from '../../../common/dao/item.dao';
import createCustomErrorLogger from '../../../common/logger/error-logger';
import validateImage from '../../../common/helpers/validate-image';
import { FindOrCreateExciseHashUseCase } from '../../excise-hashes/domain/use-cases/find-or-create-excise-hash.use-case';
import checkDiskSpace from 'check-disk-space';
import { UserDao } from '../../../common/dao/user.dao';
import testConfig from '../../../config/test.config';
import { formatCheckDataToResponse } from '../../../common/helpers/dataToResponse/checks-data-to-response';
import * as substr from 'locutus/php/strings/substr';
import { createLogger } from 'winston';

@Injectable()
export class ChecksService {
  private readonly KGD_VALUES = ['serial_number', 'excise_code'];
  private readonly SERVICE_URL = 'http://wipon.net:5007/?service=';

  private readonly Base64_SAVE_SUBDIRECTORY = 'sticker_photos';

  private readonly CRC_TABLE = [
    0x0, 0xc0c1, 0xc181, 0x140, 0xc301, 0x3c0, 0x280, 0xc241, 0xc601, 0x6c0, 0x780, 0xc741, 0x500, 0xc5c1, 0xc481,
    0x440, 0xcc01, 0xcc0, 0xd80, 0xcd41, 0xf00, 0xcfc1, 0xce81, 0xe40, 0xa00, 0xcac1, 0xcb81, 0xb40, 0xc901, 0x9c0,
    0x880, 0xc841, 0xd801, 0x18c0, 0x1980, 0xd941, 0x1b00, 0xdbc1, 0xda81, 0x1a40, 0x1e00, 0xdec1, 0xdf81, 0x1f40,
    0xdd01, 0x1dc0, 0x1c80, 0xdc41, 0x1400, 0xd4c1, 0xd581, 0x1540, 0xd701, 0x17c0, 0x1680, 0xd641, 0xd201, 0x12c0,
    0x1380, 0xd341, 0x1100, 0xd1c1, 0xd081, 0x1040, 0xf001, 0x30c0, 0x3180, 0xf141, 0x3300, 0xf3c1, 0xf281, 0x3240,
    0x3600, 0xf6c1, 0xf781, 0x3740, 0xf501, 0x35c0, 0x3480, 0xf441, 0x3c00, 0xfcc1, 0xfd81, 0x3d40, 0xff01, 0x3fc0,
    0x3e80, 0xfe41, 0xfa01, 0x3ac0, 0x3b80, 0xfb41, 0x3900, 0xf9c1, 0xf881, 0x3840, 0x2800, 0xe8c1, 0xe981, 0x2940,
    0xeb01, 0x2bc0, 0x2a80, 0xea41, 0xee01, 0x2ec0, 0x2f80, 0xef41, 0x2d00, 0xedc1, 0xec81, 0x2c40, 0xe401, 0x24c0,
    0x2580, 0xe541, 0x2700, 0xe7c1, 0xe681, 0x2640, 0x2200, 0xe2c1, 0xe381, 0x2340, 0xe101, 0x21c0, 0x2080, 0xe041,
    0xa001, 0x60c0, 0x6180, 0xa141, 0x6300, 0xa3c1, 0xa281, 0x6240, 0x6600, 0xa6c1, 0xa781, 0x6740, 0xa501, 0x65c0,
    0x6480, 0xa441, 0x6c00, 0xacc1, 0xad81, 0x6d40, 0xaf01, 0x6fc0, 0x6e80, 0xae41, 0xaa01, 0x6ac0, 0x6b80, 0xab41,
    0x6900, 0xa9c1, 0xa881, 0x6840, 0x7800, 0xb8c1, 0xb981, 0x7940, 0xbb01, 0x7bc0, 0x7a80, 0xba41, 0xbe01, 0x7ec0,
    0x7f80, 0xbf41, 0x7d00, 0xbdc1, 0xbc81, 0x7c40, 0xb401, 0x74c0, 0x7580, 0xb541, 0x7700, 0xb7c1, 0xb681, 0x7640,
    0x7200, 0xb2c1, 0xb381, 0x7340, 0xb101, 0x71c0, 0x7080, 0xb041, 0x5000, 0x90c1, 0x9181, 0x5140, 0x9301, 0x53c0,
    0x5280, 0x9241, 0x9601, 0x56c0, 0x5780, 0x9741, 0x5500, 0x95c1, 0x9481, 0x5440, 0x9c01, 0x5cc0, 0x5d80, 0x9d41,
    0x5f00, 0x9fc1, 0x9e81, 0x5e40, 0x5a00, 0x9ac1, 0x9b81, 0x5b40, 0x9901, 0x59c0, 0x5880, 0x9841, 0x8801, 0x48c0,
    0x4980, 0x8941, 0x4b00, 0x8bc1, 0x8a81, 0x4a40, 0x4e00, 0x8ec1, 0x8f81, 0x4f40, 0x8d01, 0x4dc0, 0x4c80, 0x8c41,
    0x4400, 0x84c1, 0x8581, 0x4540, 0x8701, 0x47c0, 0x4680, 0x8641, 0x8201, 0x42c0, 0x4380, 0x8341, 0x4100, 0x81c1,
    0x8081, 0x4040,
  ];

  constructor(
    @InjectRepository(ChecksRepository) private readonly checksRepository: ChecksRepository,
    private readonly httpService: HttpService,
    private readonly findUsersStore: FindUsersStoreUseCase,
    private readonly findOrCreateItem: FindOrCreateItemUseCase,
    private readonly countItemByExciseCode: CountItemByExciseCodeUseCase,
    private readonly setItemAndProductRelation: SetItemAndProductRelationUseCase,
    private readonly disassociateItemFromProduct: DisassociateItemFromProductUseCase,
    private readonly bfAuth: BfAuthenticityService,
    private readonly findOrCreateExciseHash: FindOrCreateExciseHashUseCase,
  ) {}

  async getUsersCheckWithItemProducts(
    getUsersChecksDto: GetUsersChecksDto,
    userId: number,
    currentPage: string | undefined,
    fullUrl: string,
  ) {
    const page = Number(currentPage) || 1;
    let status;
    switch (getUsersChecksDto.status) {
      case 'valid':
        status = ItemDao.ITEM_STATUS_VALID;
        break;
      case 'fake':
        status = ItemDao.ITEM_STATUS_FAKE;
        break;
      case 'atlas':
        status = ItemDao.ITEM_STATUS_ATLAS;
        break;
      default:
        status = null;
    }

    return await this.checksRepository.getUsersCheckWithItemProducts(userId, status, page, fullUrl);
  }

  async getChecksStats(user: UserDao) {
    const startOfMonth = getStartOfMonth(getNowAlmatyTime());
    const monthNumber = startOfMonth.getMonth();
    // const checksForMonth = await this.checksRepository.countUsersChecksForMonth(user.id, startOfMonth);
    // const uniqueChecksForMonth = await this.checksRepository.getUsersUniqueChecksForMonth(user.id, startOfMonth);
    const totalChecks = await this.checksRepository.countUsersChecks(user.id);
    const uniqueTotalChecks = await this.checksRepository.countUsersUniqueChecks(user.id);

    // return {
    //   month_number: monthNumber + 1,
    //   for_month: checksForMonth,
    //   for_month_unique: Number(uniqueChecksForMonth[0].amount),
    //   total: totalChecks,
    //   total_unique: Number(uniqueTotalChecks[0].amount),
    // };
    return {
      month_number: monthNumber + 1,
      for_month: 0,
      for_month_unique: 0,
      total: totalChecks,
      total_unique: Number(uniqueTotalChecks[0].amount),
    };
  }

  async validateChecksData(validateCheckData: ValidateCheckDataDto, user: UserDao) {
    const isKgd = this.KGD_VALUES.includes(validateCheckData.type);
    // await this.checkBFServiceAvailability();
    const store = await this.findUsersStore.handle(user.id);
    if (!store) {
      throw new ForbiddenException({ message: 'Store not found.' });
    }

    // сохраним изображение акцизной марки
    let stickerUri;
    if (validateCheckData.sticker_photo) {
      stickerUri = await saveBase64ImageExif(validateCheckData.sticker_photo, this.Base64_SAVE_SUBDIRECTORY);
    }

    const type = isKgd ? validateCheckData.type : substr(validateCheckData.type, 3);
    let code =
      validateCheckData.code.length >= 2 && !isKgd && type === 'excise_code'
        ? substr(validateCheckData.code, 0, 2).toUpperCase() + substr(validateCheckData.code, 2)
        : validateCheckData.code;

    code = code.replace(/ctrlAlte|tab/g, '');
    let item = await this.findOrCreateItem.handle(type, code);
    let srcRequestRequired = !['testing', 'local'].includes(appConfig.environment);
    if (!srcRequestRequired && !item.status) {
      isKgd && type === 'excise_code' ? (item.status = this.validateExciseCode(code)) : (srcRequestRequired = true);
    }

    srcRequestRequired = true;

    if (srcRequestRequired) {
      let product;
      if (type === 'excise_code' && substr(code, 0, 3) == 'U01' && !substr(code, 2, 9).match(/^\d+$/)) {
        product = null;
      } else {
        product = await this.bfAuth.requestBfProductForItem(item);
        // if (product === null && isKgd) {
        //   try {
        //     // await this.checkKgdServiceAvailability(type);
        //   } catch (e) {
        //     if (stickerUri) {
        //       fs.unlinkSync(path.resolve(this.Base64_SAVE_SUBDIRECTORY, stickerUri));
        //     }
        //     throw e;
        //   }
        //   // product = await this.bfAuth.requestProductForItem(item);
        // }
      }

      const itemsCount = await this.countItemByExciseCode.handle(type, code);
      if (!item.id && itemsCount > 0) {
        item = await this.findOrCreateItem.handle(type, code);
      }

      if (product) {
        // await this.setItemAndProductRelation.handle(item.id, product.id);
        item.product_id = product.id;
        item.status = ItemDao.ITEM_STATUS_VALID;
      } else {
        // await this.disassociateItemFromProduct.handle(item.id);
        item.product_id = null;
        item.status = ItemDao.ITEM_STATUS_FAKE;
      }
    }

    item.hash = validateCheckData.hash;
    if (item.hash && item.status === ItemDao.ITEM_STATUS_VALID) {
      try {
        let exciseDir = path.join(substr(item.hash, 0, 2), substr(item.hash, 2, 2));
        exciseDir = path.resolve('static', 'images', 'excise_photos', exciseDir);
        const isExciseDirExists = await isFileOrDirectoryExists(exciseDir);
        if (isExciseDirExists) {
          const files = await getFilesInDir(exciseDir);
          if (files && files.length) {
            files.forEach((fileName) => {
              const dotPos = fileName.indexOf('.');
              if (item.hash.length === dotPos && item.hash.localeCompare(fileName) === 0) {
                fs.unlinkSync(path.join(exciseDir, fileName));
              }
            });
          }
        }
      } catch (e) {
        const errorLogger = createCustomErrorLogger();
        errorLogger.log('error', e);
        if (stickerUri) {
          const pathToImg = path.resolve('static', 'images', stickerUri);
          const isFileExists = await isFileOrDirectoryExists(pathToImg);
          if (isFileExists) {
            await fs.promises.unlink(pathToImg);
          }
        }
        throw e;
      }
    }

    if (validateCheckData.gtin) {
      item.gtin = validateCheckData.gtin;
    }

    const itemsCount = await this.countItemByExciseCode.handle(type, code);
    if (!item.id && itemsCount > 0) {
      const exItem = await this.findOrCreateItem.handle(type, code);
      if (item.gtin !== null) {
        exItem.gtin = item.gtin;
      }
      if (exItem.product_id === null && item.product_id !== null) {
        exItem.product_id = item.product_id;
        exItem.status = ItemDao.ITEM_STATUS_VALID;
      }
      exItem.hash = item.hash;
      item = exItem;
    }

    let createdCheck;

    try {
      await getManager().transaction(async (transactionalEntityManager) => {
        const newItem = await transactionalEntityManager.save(item);
        const check = new CheckDao();
        check.longitude = validateCheckData.longitude;
        check.latitude = validateCheckData.latitude;
        check.accuracy = validateCheckData.accuracy;
        check.third_party = validateCheckData.third_party;
        check.sticker_photo = stickerUri;

        check.item_id = newItem.id;
        check.user_id = user.id;
        check.store_id = store.id;
        check.created_at = new Date();
        check.updated_at = new Date();
        createdCheck = await transactionalEntityManager.save(check);

        if (testConfig.productionwhitelist.includes(user.phone_number)) {
          if (stickerUri) {
            const pathToImg = path.resolve('static', 'images', stickerUri);
            const isFileExists = await isFileOrDirectoryExists(pathToImg);
            if (isFileExists) {
              await fs.promises.unlink(pathToImg);
            }
          }
          throw new Error('Test User');
        }
      });

      if (createdCheck.id) {
        const checksData = await this.checksRepository
          .createQueryBuilder('check')
          .where('check.id = :checkId', { checkId: createdCheck.id })
          .leftJoinAndSelect('check.item', 'item')
          .leftJoinAndSelect('item.product', 'product')
          .getOne();

        return formatCheckDataToResponse(checksData);
      }

      return createdCheck;
    } catch (e) {
      if (stickerUri) {
        const pathToImg = path.resolve('static', 'images', stickerUri);
        const isFileExists = await isFileOrDirectoryExists(pathToImg);
        if (isFileExists) {
          await fs.promises.unlink(pathToImg);
        }
      }
      throw e;
    }
  }

  async checkBFServiceAvailability() {
    try {
      await this.httpService.axiosRef.get(`${this.SERVICE_URL}bf-service`);
    } catch (e) {
      const reason = 'BF service unavailable';
      const msg = e.response?.message || e.response?.data?.message || 'messageNotFound';
      throw new HttpException(`${reason}: ${msg}`, 424);
    }
  }

  validateExciseCode(hash: string): number {
    if (hash.length === 57 && substr(hash, 0, 2) === '55') {
      return ItemDao.ITEM_STATUS_ATLAS;
    }

    if (hash.length !== 47) {
      return ItemDao.ITEM_STATUS_FAKE;
    }

    let crc = 0xffff;
    const str = substr(hash, 43, 4);

    for (let i = 0; i < str.length; i++) {
      crc = (crc >> 8) ^ this.CRC_TABLE[(crc & 0xff) ^ str[i].charCodeAt(0)];
    }

    const exciseCrc = parseInt(substr(hash, 43, 4), 16);

    return exciseCrc == crc ? ItemDao.ITEM_STATUS_VALID : ItemDao.ITEM_STATUS_FAKE;
  }

  async checkKgdServiceAvailability(type: string) {
    try {
      const service = type === 'excise_code' ? 'wipon-service-guid' : 'wipon-service';
      await this.httpService.axiosRef.get(this.SERVICE_URL + service);
    } catch (e) {
      const reason = 'KGD service unavailable';
      const msg = e.response?.message || '';
      throw new HttpException(`${reason} : ${msg}`, 424);
    }
  }

  async storeChecksPicture(storeChecksPictureDto: StoreChecksPictureDto, user: UserDao, image: Express.Multer.File) {
    this.checkIsValidImage(image);
    const fileName = `${storeChecksPictureDto.hash}.${path.extname(image.originalname)}`;
    try {
      await getManager().transaction(async (transactionalEntityManager) => {
        const exciseHash = await this.findOrCreateExciseHash.handle(storeChecksPictureDto.hash);
        exciseHash.saved_at = new Date();
        await transactionalEntityManager.save(exciseHash);
        const exciseDir = path.join(substr(fileName, 0, 2), substr(fileName, 2, 2));
        const fullPath = path.resolve('static', 'images', 'excise_photos', exciseDir);
        const diskSpace = await checkDiskSpace(fullPath);
        if (diskSpace.free < image.size) {
          throw new HttpException({ error: 'Disk space not enough' }, 507);
        }
        const isExciseDirExists = await isFileOrDirectoryExists(path.join(fullPath, fileName));
        if (isExciseDirExists) {
          await fs.promises.unlink(path.join(fullPath, fileName));
        }
        await fs.promises.mkdir(fullPath, { recursive: true });
        await fs.promises.writeFile(path.join(fullPath, fileName), image.buffer);
      });
    } catch (e) {
      const errorLogger = createLogger();
      errorLogger.log('error', e);
      throw new HttpException({ error: 'Can not store the file' }, 500);
    }
    return { status: 'success' };
  }

  private checkIsValidImage(image: Express.Multer.File) {
    if (!image) throw new HttpException({ photo: 'The photo file is not uploaded' }, 422);
    if (!image.originalname.match(/\.(jpg|jpeg|png|gif)$/)) {
      throw new HttpException({ photo: 'The photo file was not uploaded validly' }, 422);
    }
    if (!validateImage(image.path)) {
      throw new HttpException({ photo: 'The photo file was not uploaded validly' }, 422);
    }
  }
}
