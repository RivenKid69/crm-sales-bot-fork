import { HttpException, Injectable } from '@nestjs/common';
import { versionResponseType } from '../../../common/types/responses/version-response.type';
import {
  MOBILE_CURRENT_VERSION,
  MOBILE_LAST_VERSION_OF_MAJOR_UPDATE,
  UPDATE_NOT_REQUIRED,
  UPDATE_REQUIRED,
  UPDATE_URL_IOS,
  UPDATE_URL_DESKTOP,
  DESKTOP_CURRENT_VERSION,
  DESKTOP_LAST_VERSION_OF_MAJOR_UPDATE,
  UPDATE_PARTLY_REQUIRED,
} from '../../../config/version.config';

@Injectable()
export class VersionService {
  getDesktopVersion(versionOfUser: string): versionResponseType {
    if (!versionOfUser || isNaN(Number(versionOfUser))) throw new HttpException('version must be numeric value', 400);

    const response: versionResponseType = {
      type: UPDATE_NOT_REQUIRED,
      version: DESKTOP_CURRENT_VERSION,
      title: 'Проверка наличия обновлений',
      message: 'Версия вашего приложения является актуальной',
      update_url: '',
    };

    const usersCurrentVersion = Number(versionOfUser);
    if (usersCurrentVersion >= DESKTOP_CURRENT_VERSION) return response;

    response.update_url = UPDATE_URL_DESKTOP;
    if (usersCurrentVersion < DESKTOP_CURRENT_VERSION && usersCurrentVersion >= DESKTOP_LAST_VERSION_OF_MAJOR_UPDATE) {
      response.type = UPDATE_PARTLY_REQUIRED;
      response.message = 'Версия вашего приложения устарела, советуем обновить приложение';
    } else if (
      usersCurrentVersion < DESKTOP_CURRENT_VERSION &&
      usersCurrentVersion < DESKTOP_LAST_VERSION_OF_MAJOR_UPDATE
    ) {
      response.type = UPDATE_REQUIRED;
      response.message = 'Версия вашего приложения устарела, необходимо обновить приложение для корректной работы';
    }

    return response;
  }

  getMobileVersion(versionOfUser: string): versionResponseType {
    if (!versionOfUser || isNaN(Number(versionOfUser))) throw new HttpException('version must be numeric value', 400);

    const response: versionResponseType = {
      type: UPDATE_NOT_REQUIRED,
      version: MOBILE_CURRENT_VERSION,
      title: 'Проверка наличия обновлений',
      message: 'Версия вашего приложения является актуальной',
      update_url: '',
    };

    const usersCurrentVersion = Number(versionOfUser);
    if (usersCurrentVersion >= MOBILE_CURRENT_VERSION) return response;

    response.update_url = UPDATE_URL_IOS;
    if (usersCurrentVersion < MOBILE_CURRENT_VERSION && usersCurrentVersion >= MOBILE_LAST_VERSION_OF_MAJOR_UPDATE) {
      response.message = 'Версия вашего приложения устарела, советуем обновить приложение';
    } else if (
      usersCurrentVersion < MOBILE_CURRENT_VERSION &&
      usersCurrentVersion < MOBILE_LAST_VERSION_OF_MAJOR_UPDATE
    ) {
      response.type = UPDATE_REQUIRED;
      response.message = 'Версия вашего приложения устарела, необходимо обновить приложение для корректной работы';
    }

    return response;
  }
}
