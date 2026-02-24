import { IsInt, IsNotEmpty, IsOptional, IsPhoneNumber, Min } from 'class-validator';
import { IsPhoneExistsInUsers } from '../../../common/validations/is-entity-exists';

export class StoreSubscriptionDto {
  @IsNotEmpty()
  @IsPhoneNumber('KZ')
  @IsPhoneExistsInUsers({
    message: 'User with phone number: $value not found',
  })
  phone_number: string;

  @IsOptional()
  @IsInt()
  @Min(1)
  lifetime: number;
}
