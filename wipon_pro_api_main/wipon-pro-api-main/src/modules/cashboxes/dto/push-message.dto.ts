import { IsNotEmpty, IsPhoneNumber, IsString } from 'class-validator';

export class PushMessageDto {
  @IsNotEmpty()
  @IsString()
  @IsPhoneNumber('KZ')
  phone_number: string;

  @IsNotEmpty()
  @IsString()
  message: string;
}
