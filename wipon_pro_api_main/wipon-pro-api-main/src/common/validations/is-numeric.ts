import {
  registerDecorator,
  ValidationArguments,
  ValidationOptions,
  ValidatorConstraint,
  ValidatorConstraintInterface,
} from 'class-validator';

@ValidatorConstraint()
class IsNumericConstraint implements ValidatorConstraintInterface {
  validate(value: string) {
    return !isNaN(Number(value));
  }

  defaultMessage(validationArguments?: ValidationArguments): string {
    return `${validationArguments?.property} must be numeric value`;
  }
}

export function IsNumeric(validationOptions?: ValidationOptions) {
  return function (object: Record<string, any>, propertyName: string) {
    registerDecorator({
      target: object.constructor,
      propertyName: propertyName,
      options: validationOptions,
      constraints: [],
      validator: IsNumericConstraint,
    });
  };
}
