import { HttpException, Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { StoresRepository } from '../data/stores.repository';
import { FindRegionByNameUseCase } from '../../regions/domain/use-cases/find-region-by-name.use-case';
import { RegionDao } from '../../../common/dao/region.dao';
import { PostOrUpdateStoreDto } from '../dto/post-or-update-store.dto';
import { validateOrReject } from 'class-validator';
import { NewFormOfSavingStoreDto } from '../dto/new-form-of-saving-store.dto';
import { getManager, Not } from 'typeorm';
import { OldFormOfSavingStoreWithRegionDto } from '../dto/old-form-of-saving-store-with-region.dto';
import { FindRegionByIdUseCase } from '../../regions/domain/use-cases/find-region-by-id.use-case';
import { FindDgdByNameUseCase } from '../../dgds/domain/use-cases/find-dgd-by-name.use-case';
import { DgdDao } from '../../../common/dao/dgd.dao';
import { OldFormOfSavingStoreWithoutRegionDto } from '../dto/old-form-of-saving-store-without-region.dto';
import { GetCheckDto } from '../dto/get-check.dto';
import { CountUsersActiveSubscriptionUseCase } from '../../subscriptions/domain/use-cases/count-users-active-subscription.use-case';
import { UserDao } from '../../../common/dao/user.dao';
import { StoreDao } from '../../../common/dao/store.dao';
import { UpdateStoreAndUserNameDto } from '../dto/update-store-and-user-name.dto';

@Injectable()
export class StoresService {
  private readonly gdgRegions = {
    '1801': 'Восточно-Казахстанская область',
    '0601': 'Актюбинская область',
    '0901': 'Алматинская область',
    '2101': 'Жамбылская область',
    '1501': 'Атырауская область',
    '3001': 'Карагандинская область',
    '3301': 'Кызылординская область',
    '3901': 'Костанайская область',
    '4301': 'Мангистауская область',
    '4501': 'Павлодарская область',
    '4801': 'Северо-Казахстанская область',
    '5801': 'Туркестанская область',
    '5901': 'Шымкент',
    '2701': 'Западно-Казахстанская область',
    '0301': 'Акмолинская область',
    '6201': 'Нур-Султан (Астана)',
    '6001': 'Алматы',
  };

  constructor(
    @InjectRepository(StoresRepository) private readonly storesRepo: StoresRepository,
    private readonly findRegionByName: FindRegionByNameUseCase,
    private readonly findRegionById: FindRegionByIdUseCase,
    private readonly findDgdByName: FindDgdByNameUseCase,
    private readonly countUsersActiveSubscription: CountUsersActiveSubscriptionUseCase,
  ) {}

  async getCheck(getCheckDto: GetCheckDto) {
    let result = false;
    const getCheckValidation = new GetCheckDto();
    getCheckValidation.license_number = getCheckDto.license_number;

    try {
      await validateOrReject(getCheckValidation);
    } catch (errors) {
      return { status: result };
    }

    const store = await this.storesRepo.findOne({
      where: { license_number: getCheckDto.license_number },
      relations: ['user'],
    });

    if (store && store.user) {
      const subscriptions = await this.countUsersActiveSubscription.handle(store.user.id);
      result = !!subscriptions;
    }

    return {
      status: result,
    };
  }

  async getUsersStore(userId: number) {
    const store = await this.storesRepo.findOne({
      where: { user_id: userId },
      relations: ['buisnessStoreType', 'dgd', 'ugd', 'user'],
    });
    if (!store) return null;
    const regionName = this.gdgRegions[store.buisness_dgd_id];
    let region: undefined | RegionDao = undefined;
    if (regionName) {
      region = await this.findRegionByName.handle(regionName);
    }
    return { ...store, region, buisness_store_type: store.buisnessStoreType };
  }

  async postOrUpdateStore(userId: number, storeDto: PostOrUpdateStoreDto) {
    const store = await this.storesRepo.findOne({ where: { user_id: userId } });
    let data;
    if (!(storeDto.region_id || storeDto.bin)) {
      if (storeDto.buisness_bin && storeDto.buisness_bin.match(/^\d{1,12}$/)) {
        storeDto.buisness_bin = this.addZerosToBin(storeDto.buisness_bin);
      }

      if (storeDto.payer_bin && storeDto.payer_bin.match(/^\d{1,12}$/)) {
        storeDto.payer_bin = this.addZerosToBin(storeDto.payer_bin);
      }

      const newFormOfSavingStore = this.getValidationObjectOfNewForm(storeDto);
      try {
        await validateOrReject(newFormOfSavingStore);
      } catch (errors) {
        throw new HttpException({ errors }, 422);
      }

      if (store) await this.validateIsEmailUniqueInStores(newFormOfSavingStore.payer_email, store.id);
      else await this.validateIsEmailUniqueInStores(newFormOfSavingStore.payer_email);

      data = storeDto;
    } else {
      // old registration
      if (storeDto.bin && storeDto.bin.match(/^\d${1,12}$/)) {
        storeDto.bin = this.addZerosToBin(storeDto.bin);
      }
      data = storeDto;

      if (storeDto.region_id) {
        const oldFormOfSavingStoreWithRegion = this.getValidationObjectOfOldFormWithRegion(storeDto);
        try {
          await validateOrReject(oldFormOfSavingStoreWithRegion);
        } catch (errors) {
          throw new HttpException({ errors }, 422);
        }

        const dgd = await this.getDgdByRegion(storeDto.region_id);
        if (dgd) {
          data.buisness_dgd_id = dgd.id;
        }
      } else {
        const oldFormOfSavingStoreWithoutRegion = this.getValidationObjectOfOldFormWithoutRegion(storeDto);
        try {
          await validateOrReject(oldFormOfSavingStoreWithoutRegion);
        } catch (errors) {
          throw new HttpException({ errors }, 422);
        }
      }

      data.buisness_store_type_id = data.store_type_id;
      delete data.store_type_id;
      data.buisness_full_legal_name = data.legal_name;
      delete data.legal_name;
      data.payer_name = data.buisness_full_legal_name;
      data.buisness_bin = data.bin;
      delete data.bin;
      data.payer_bin = data.buisness_bin;
      if (data.name) {
        data.buisness_store_name = data.name;
        delete data.name;
      }
      if (data.longitude) {
        delete data.longitude;
      }
      if (data.latitude) {
        delete data.latitude;
      }

      if (storeDto.address) {
        data.buisness_store_address = storeDto.address;
        data.payer_address = storeDto.address;
        data.payer_postal_address = storeDto.address;
      } else if (storeDto.city && storeDto.street && storeDto.house) {
        data.buisness_store_address = `${storeDto.city} ${storeDto.street} ${storeDto.house}`;
        data.payer_address = data.buisness_store_address;
        data.payer_postal_address = data.buisness_store_address;
      }

      if (data.address) {
        delete data.address;
      }
      if (data.city) {
        delete data.city;
      }
      if (data.street) {
        delete data.street;
      }
      if (data.house) {
        delete data.house;
      }
    }

    const foundStore = await this.storesRepo.findOne({ user_id: userId });
    if (foundStore) {
      if (data.user_id) delete data.user_id;
      await this.storesRepo.update({ user_id: userId }, { updated_at: new Date(), ...data });
      return {
        status: 'success',
      };
    }

    await this.storesRepo.save({ user_id: userId, created_at: new Date(), ...data });

    return {
      status: 'success',
    };
  }

  async saveOrUpdateStore(userId: number, storeDto: PostOrUpdateStoreDto) {
    await this.storesRepo.save({ user_id: userId, created_at: new Date(), ...storeDto });
    return {
      status: 'success',
    };
  }

  async updateStoreAndUserName(user: UserDao, updateStoreAndUserNameDto: UpdateStoreAndUserNameDto) {
    try {
      await getManager().transaction(async (transactionalEntityManager) => {
        await transactionalEntityManager.update(
          StoreDao,
          { user_id: user.id },
          {
            buisness_full_legal_name: updateStoreAndUserNameDto.buisness_full_legal_name,
            buisness_store_address: updateStoreAndUserNameDto.buisness_store_address,
            buisness_store_name: updateStoreAndUserNameDto.buisness_store_name,
            updated_at: new Date(),
          },
        );
        await transactionalEntityManager.update(
          UserDao,
          { id: user.id },
          {
            name: updateStoreAndUserNameDto.name,
            updated_at: new Date(),
          },
        );
      });
    } catch (e) {
      throw new HttpException("Can't update user data", 500);
    }
    return {
      status: 'success',
    };
  }

  private addZerosToBin(bin: string): string {
    while (bin.length < 12) {
      bin = `0${bin}`;
    }
    return bin;
  }

  private async getDgdByRegion(regionId: number): Promise<DgdDao | null> {
    const region = await this.findRegionById.handle(regionId);
    if (!region) return null;
    let dgdName: string | null;
    switch (region.name_ru) {
      case 'Восточно-Казахстанская область':
        dgdName = 'ДГД по Восточно-Казахстанской области';
        break;
      case 'Актюбинская область':
        dgdName = 'ДГД по Актюбинской области';
        break;
      case 'Алматинская область':
        dgdName = 'ДГД по Алматинской области';
        break;
      case 'Жамбылская область':
        dgdName = 'ДГД по Жамбылской области';
        break;
      case 'Атырауская область':
        dgdName = 'ДГД по Атырауской области';
        break;
      case 'Карагандинская область':
        dgdName = 'ДГД по Карагандинской области';
        break;
      case 'Кызылординская область':
        dgdName = 'ДГД по Кызылординской области';
        break;
      case 'Костанайская область':
        dgdName = 'ДГД по Костанайской области';
        break;
      case 'Мангистауская область':
        dgdName = 'ДГД по Мангистауской области';
        break;
      case 'Павлодарская область':
        dgdName = 'ДГД по Павлодарской области';
        break;
      case 'Северо-Казахстанская область':
        dgdName = 'ДГД по Северо-Казахстанской области';
        break;
      case 'Туркестанская область':
        dgdName = 'ДГД по Туркестанской области';
        break;
      case 'Шымкент':
        dgdName = 'ДГД по г.Шымкент';
        break;
      case 'Западно-Казахстанская область':
        dgdName = 'ДГД по Западно-Казахстанской области';
        break;
      case 'Акмолинская область':
        dgdName = 'ДГД по Акмолинской области';
        break;
      case 'Нур-Султан (Астана)':
        dgdName = 'ДГД по г.Нур-Султан (Астана)';
        break;
      case 'Алматы':
        dgdName = 'ДГД по г.Алматы';
        break;
      default:
        dgdName = null;
    }

    if (!dgdName) return null;

    return await this.findDgdByName.handle(dgdName);
  }

  private getValidationObjectOfNewForm(storeDto: PostOrUpdateStoreDto): NewFormOfSavingStoreDto {
    const newFormOfSavingStore = new NewFormOfSavingStoreDto();
    newFormOfSavingStore.buisness_store_type_id = storeDto.buisness_store_type_id;
    newFormOfSavingStore.buisness_dgd_id = storeDto.buisness_dgd_id;
    newFormOfSavingStore.payer_bin = storeDto.payer_bin;
    newFormOfSavingStore.payer_name = storeDto.payer_name;
    newFormOfSavingStore.payer_address = storeDto.payer_address;
    newFormOfSavingStore.payer_postal_address = storeDto.payer_postal_address;
    newFormOfSavingStore.buisness_bin = storeDto.buisness_bin;
    newFormOfSavingStore.license_number = storeDto.license_number;
    newFormOfSavingStore.buisness_store_address = storeDto.buisness_store_address;
    newFormOfSavingStore.buisness_full_legal_name = storeDto.buisness_full_legal_name;
    newFormOfSavingStore.buisness_store_name = storeDto.buisness_store_name;
    newFormOfSavingStore.buisness_ugd_id = storeDto.buisness_ugd_id;
    newFormOfSavingStore.payer_email = storeDto.payer_email;
    return newFormOfSavingStore;
  }

  private getValidationObjectOfOldFormWithoutRegion(
    storeDto: PostOrUpdateStoreDto,
  ): OldFormOfSavingStoreWithoutRegionDto {
    const oldFormOfSavingStoreWithoutRegion = new OldFormOfSavingStoreWithoutRegionDto();
    oldFormOfSavingStoreWithoutRegion.buisness_dgd_id = storeDto.buisness_dgd_id;
    oldFormOfSavingStoreWithoutRegion.buisness_ugd_id = storeDto.buisness_ugd_id;
    oldFormOfSavingStoreWithoutRegion.store_type_id = storeDto.store_type_id;
    oldFormOfSavingStoreWithoutRegion.name = storeDto.name;
    oldFormOfSavingStoreWithoutRegion.bin = storeDto.bin;
    oldFormOfSavingStoreWithoutRegion.legal_name = storeDto.legal_name;
    oldFormOfSavingStoreWithoutRegion.license_number = storeDto.license_number;
    oldFormOfSavingStoreWithoutRegion.address = storeDto.address;
    return oldFormOfSavingStoreWithoutRegion;
  }

  private getValidationObjectOfOldFormWithRegion(storeDto: PostOrUpdateStoreDto): OldFormOfSavingStoreWithRegionDto {
    const oldFormOfSavingStoreWithRegion = new OldFormOfSavingStoreWithRegionDto();
    oldFormOfSavingStoreWithRegion.region_id = storeDto.region_id;
    oldFormOfSavingStoreWithRegion.store_type_id = storeDto.store_type_id;
    oldFormOfSavingStoreWithRegion.city = storeDto.city;
    oldFormOfSavingStoreWithRegion.street = storeDto.street;
    oldFormOfSavingStoreWithRegion.house = storeDto.house;
    oldFormOfSavingStoreWithRegion.name = storeDto.name;
    oldFormOfSavingStoreWithRegion.bin = storeDto.bin;
    oldFormOfSavingStoreWithRegion.legal_name = storeDto.legal_name;
    oldFormOfSavingStoreWithRegion.license_number = storeDto.license_number;
    oldFormOfSavingStoreWithRegion.address = storeDto.address;
    return oldFormOfSavingStoreWithRegion;
  }

  private async validateIsEmailUniqueInStores(email: string, storeId?: number): Promise<void> {
    if (!email) return;
    // let options;
    // storeId
    //   ? (options = { where: { payer_email: email, id: Not(storeId) } })
    //   : (options = { where: { payer_email: email } });
    // const stores = await this.storesRepo.count(options);
    // if (stores) throw new HttpException({ message: `Email ${email} уже существует в системе` }, 422);
  }
}
