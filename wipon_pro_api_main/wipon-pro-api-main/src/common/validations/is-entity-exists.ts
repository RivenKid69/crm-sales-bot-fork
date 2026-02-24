import {
  registerDecorator,
  ValidationOptions,
  ValidatorConstraint,
  ValidatorConstraintInterface,
} from 'class-validator';
import { StoreTypeDao } from '../dao/store-type.dao';
import { DgdDao } from '../dao/dgd.dao';
import { UgdDao } from '../dao/ugd.dao';
import { RegionDao } from '../dao/region.dao';
import { ItemDao } from '../dao/item.dao';
import { UserDao } from '../dao/user.dao';
import { LedgerDao } from '../dao/ledger.dao';

@ValidatorConstraint({ async: true })
class IsStoreTypeExistsConstraint implements ValidatorConstraintInterface {
  validate(storeTypeId: number) {
    return StoreTypeDao.count({ where: { id: storeTypeId } }).then((value) => !!value);
  }
}

export function IsStoreTypeExists(validationOptions?: ValidationOptions) {
  return function (object: Object, propertyName: string) {
    registerDecorator({
      target: object.constructor,
      propertyName: propertyName,
      options: validationOptions,
      constraints: [],
      validator: IsStoreTypeExistsConstraint,
    });
  };
}

@ValidatorConstraint({ async: true })
class IsDgdExistsConstraint implements ValidatorConstraintInterface {
  validate(dgdId: string) {
    return DgdDao.count({ where: { id: dgdId } }).then((value) => !!value);
  }
}

export function IsDgdExists(validationOptions?: ValidationOptions) {
  return function (object: Object, propertyName: string) {
    registerDecorator({
      target: object.constructor,
      propertyName: propertyName,
      options: validationOptions,
      constraints: [],
      validator: IsDgdExistsConstraint,
    });
  };
}

@ValidatorConstraint({ async: true })
class IsUgdExistsConstraint implements ValidatorConstraintInterface {
  validate(ugdId: string) {
    return UgdDao.count({ where: { id: ugdId } }).then((value) => !!value);
  }
}

export function IsUgdExists(validationOptions?: ValidationOptions) {
  return function (object: Object, propertyName: string) {
    registerDecorator({
      target: object.constructor,
      propertyName: propertyName,
      options: validationOptions,
      constraints: [],
      validator: IsUgdExistsConstraint,
    });
  };
}

@ValidatorConstraint({ async: true })
class IsRegionExistsConstraint implements ValidatorConstraintInterface {
  validate(regionId: number) {
    return RegionDao.count({ where: { id: regionId } }).then((value) => !!value);
  }
}

export function IsRegionExists(validationOptions?: ValidationOptions) {
  return function (object: Object, propertyName: string) {
    registerDecorator({
      target: object.constructor,
      propertyName: propertyName,
      options: validationOptions,
      constraints: [],
      validator: IsRegionExistsConstraint,
    });
  };
}

@ValidatorConstraint({ async: true })
class IsItemExistsConstraint implements ValidatorConstraintInterface {
  validate(itemId: number) {
    return ItemDao.count({ where: { id: itemId } }).then((value) => !!value);
  }
}

export function IsItemExists(validationOptions?: ValidationOptions) {
  return function (object: Object, propertyName: string) {
    registerDecorator({
      target: object.constructor,
      propertyName: propertyName,
      options: validationOptions,
      constraints: [],
      validator: IsItemExistsConstraint,
    });
  };
}

@ValidatorConstraint({ async: true })
class IsIPhoneNumberExistsConstraint implements ValidatorConstraintInterface {
  validate(phoneNumber: string) {
    return UserDao.count({ where: { phone_number: phoneNumber } }).then((value) => !!value);
  }
}

export function IsPhoneExistsInUsers(validationOptions?: ValidationOptions) {
  return function (object: Object, propertyName: string) {
    registerDecorator({
      target: object.constructor,
      propertyName: propertyName,
      options: validationOptions,
      constraints: [],
      validator: IsIPhoneNumberExistsConstraint,
    });
  };
}

@ValidatorConstraint({ async: true })
class IsLedgerExistsConstraint implements ValidatorConstraintInterface {
  validate(ledgerId: number) {
    return LedgerDao.count({ where: { id: ledgerId } }).then((value) => !!value);
  }
}

export function IsLedgerExists(validationOptions?: ValidationOptions) {
  return function (object: Object, propertyName: string) {
    registerDecorator({
      target: object.constructor,
      propertyName: propertyName,
      options: validationOptions,
      constraints: [],
      validator: IsLedgerExistsConstraint,
    });
  };
}
